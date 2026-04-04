"""Minimal JWT auth endpoints for GUI login flow.

The S3M-GUI sends Authorization: Bearer <token> on every request.
These endpoints issue and validate tokens. In production, replace
the static user store with LDAP/AD integration.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

auth_router = APIRouter(prefix="/auth", tags=["GUI Auth"])

# ---- Config ----
_JWT_SECRET = "s3m-sovereign-key-replace-in-production"
_TOKEN_EXPIRY_SECONDS = 28800  # 8 hours

# ---- Static user store (replace with LDAP/AD in production) ----
_USERS = {
    "commander": {"password_hash": hashlib.sha256(b"s3m-cmd-2026").hexdigest(), "role": "commander", "name": "CDR Al-Rashid"},
    "analyst": {"password_hash": hashlib.sha256(b"s3m-analyst-2026").hexdigest(), "role": "analyst", "name": "CPT Al-Harbi"},
    "viewer": {"password_hash": hashlib.sha256(b"s3m-viewer-2026").hexdigest(), "role": "viewer", "name": "LT Al-Qahtani"},
    "admin": {"password_hash": hashlib.sha256(b"s3m-admin-2026").hexdigest(), "role": "admin", "name": "System Admin"},
}


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


def _sign_token(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig_input = f"{header}.{body}".encode()
    sig = base64.urlsafe_b64encode(
        hmac.new(_JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{body}.{sig}"


def _verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        sig_input = f"{parts[0]}.{parts[1]}".encode()
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(_JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(expected_sig, parts[2]):
            return None
        padding = 4 - len(parts[1]) % 4
        body = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
        if body.get("exp", 0) < time.time():
            return None
        return body
    except Exception:
        return None


def get_current_user(request: Request) -> dict:
    """FastAPI dependency — extracts and validates JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header[7:]
    payload = _verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


@auth_router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = _USERS.get(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    password_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if not hmac.compare_digest(password_hash, user["password_hash"]):
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
    token = _sign_token(payload)
    return TokenResponse(
        token=token,
        expiresAt=datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        user={"username": req.username, "name": user["name"], "role": user["role"]},
    )


@auth_router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return UserInfo(username=user["sub"], name=user["name"], role=user["role"])
