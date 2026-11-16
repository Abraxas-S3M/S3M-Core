"""JWT auth endpoints for the S3M-GUI login flow.

Military/tactical context:
The GUI bridge fronts command, analyst and admin workflows, so a forged token is
equivalent to an operator seat. No signing key or credential may live in source:
this repository is public and every deployment would otherwise share them.

Configuration (all via environment, never committed):

* ``S3M_GUI_JWT_SECRET`` - HMAC-SHA256 signing key, at least 32 characters.
  If unset, a random per-process key is generated and a warning is logged;
  tokens then stop validating on restart (fail safe, never a shared constant).
* ``S3M_GUI_USERS_FILE`` - path to a JSON user store::

      {"analyst": {"password_hash": "pbkdf2_sha256$600000$<salt>$<hash>",
                   "role": "analyst", "name": "Duty Analyst"}}

  Generate a hash with ``python -m src.api.gui_bridge.auth_routes hash-password``.
  If unset or unreadable, the store is empty and every login is rejected
  (fail closed). Replace with LDAP/AD for production.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["GUI Auth"])

# ---- Config ----
_TOKEN_EXPIRY_SECONDS = 28800  # 8 hours, one operator shift
_MIN_SIGNING_KEY_CHARS = 32
_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
_HASH_SCHEME = "pbkdf2_sha256"

_lock = threading.Lock()
_jwt_secret: Optional[bytes] = None
_users: Optional[Dict[str, dict]] = None


def _get_jwt_secret() -> bytes:
    global _jwt_secret
    with _lock:
        if _jwt_secret is None:
            configured = os.environ.get("S3M_GUI_JWT_SECRET", "")
            if len(configured) >= _MIN_SIGNING_KEY_CHARS:
                _jwt_secret = configured.encode()
            else:
                if configured:
                    logger.error(
                        "S3M_GUI_JWT_SECRET is shorter than %d chars; ignoring it", _MIN_SIGNING_KEY_CHARS
                    )
                logger.warning(
                    "S3M_GUI_JWT_SECRET not set: using an ephemeral per-process signing key. "
                    "Tokens will be invalidated on restart and across workers."
                )
                _jwt_secret = secrets.token_bytes(48)
        return _jwt_secret


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """Return a salted PBKDF2-HMAC-SHA256 hash string for the user store."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "$".join(
        (
            _HASH_SCHEME,
            str(iterations),
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, hash_b64 = stored.split("$")
        if scheme != _HASH_SCHEME:
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Constant-cost dummy so unknown usernames take the same time as wrong passwords.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16), iterations=_PBKDF2_ITERATIONS)


def _load_users() -> Dict[str, dict]:
    path = os.environ.get("S3M_GUI_USERS_FILE", "").strip()
    if not path:
        logger.warning("S3M_GUI_USERS_FILE not set: GUI login is disabled (no users).")
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot read S3M_GUI_USERS_FILE (%s); GUI login disabled.", type(exc).__name__)
        return {}
    users: Dict[str, dict] = {}
    if isinstance(raw, dict):
        for username, rec in raw.items():
            if (
                isinstance(username, str)
                and isinstance(rec, dict)
                and isinstance(rec.get("password_hash"), str)
                and rec["password_hash"].startswith(_HASH_SCHEME + "$")
                and isinstance(rec.get("role"), str)
            ):
                users[username] = {
                    "password_hash": rec["password_hash"],
                    "role": rec["role"],
                    "name": str(rec.get("name", username)),
                }
            else:
                logger.error("Skipping malformed user record %r in S3M_GUI_USERS_FILE", username)
    return users


def _get_users() -> Dict[str, dict]:
    global _users
    with _lock:
        if _users is None:
            _users = _load_users()
        return _users


def reload_auth_config() -> None:
    """Re-read secret and user store from the environment (tests, SIGHUP handlers)."""
    global _jwt_secret, _users
    with _lock:
        _jwt_secret = None
        _users = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    expiresAt: str
    user: dict


class UserInfo(BaseModel):
    username: str
    name: str
    role: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign_token(payload: dict) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(_get_jwt_secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header = json.loads(_b64decode(parts[0]))
        if header.get("alg") != "HS256":
            return None
        expected_sig = _b64(
            hmac.new(_get_jwt_secret(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(expected_sig, parts[2]):
            return None
        body = json.loads(_b64decode(parts[1]))
        if body.get("exp", 0) < time.time():
            return None
        # Token must still map to a configured user with the same role.
        user = _get_users().get(body.get("sub", ""))
        if user is None or user["role"] != body.get("role"):
            return None
        return body
    except Exception:
        return None


def get_current_user(request: Request) -> dict:
    """FastAPI dependency - extracts and validates JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    payload = _verify_token(auth_header[7:])
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


@auth_router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = _get_users().get(req.username)
    stored = user["password_hash"] if user else _DUMMY_HASH
    if not verify_password(req.password, stored) or user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    now = time.time()
    expires = now + _TOKEN_EXPIRY_SECONDS
    payload = {
        "sub": req.username,
        "role": user["role"],
        "name": user["name"],
        "iat": int(now),
        "exp": int(expires),
    }
    return TokenResponse(
        token=_sign_token(payload),
        expiresAt=datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        user={"username": req.username, "name": user["name"], "role": user["role"]},
    )


@auth_router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return UserInfo(username=user["sub"], name=user["name"], role=user["role"])


def _cli(argv: list[str]) -> int:
    if argv[:1] != ["hash-password"]:
        print("usage: python -m src.api.gui_bridge.auth_routes hash-password", file=sys.stderr)
        return 2
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat: "):
        print("Passwords do not match", file=sys.stderr)
        return 1
    print(hash_password(pw))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
