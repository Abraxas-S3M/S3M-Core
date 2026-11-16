"""Authentication for the Cortex control-plane MCP contract.

Military/tactical context:
Three keys, three authorities, so no single compromise grants write power:

* Authorisation Server (AS) key - signs 5-minute access tokens (RFC 9068 JWT profile)
  for a registered Cortex client that proved possession of its own key (RFC 7523
  private_key_jwt). Tokens are sender-constrained with DPoP (RFC 9449): a stolen token
  is useless without the client's private key. Audience = the MCP resource (RFC 8707).
* Approval Authority key - signs a per-change approval token only after out-of-band human
  device approvals. It binds the exact tool, argument digest, client and expiry, and is
  single-use. Cortex never holds this key.
* Control-plane receipt key - signs what was actually applied (see the reference server).

This module is the sandbox reference implementation (in-process). Production replaces
the AS with the customer or XiiD identity provider exposing the same token profile.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.cortex.mcp_contract.manifest import args_sha256

ACCESS_TOKEN_TTL = 300
MAX_APPROVAL_TTL = 900
CLOCK_SKEW = 30
DPOP_MAX_AGE = 60


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def public_jwk(public_key: Ed25519PublicKey) -> Dict[str, str]:
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": b64url(raw)}


def jwk_thumbprint(jwk: Mapping[str, str]) -> str:
    """RFC 7638 thumbprint for an OKP key."""
    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]}, separators=(",", ":"), sort_keys=True)
    return b64url(hashlib.sha256(canonical.encode("utf-8")).digest())


def public_key_from_jwk(jwk: Mapping[str, str]) -> Ed25519PublicKey:
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise AuthError("DPOP_INVALID", "only Ed25519 OKP keys are accepted")
    return Ed25519PublicKey.from_public_bytes(b64url_decode(jwk["x"]))


class ReplayCache:
    """Remembers single-use identifiers until their expiry."""

    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_add(self, key: str, expires_at: float) -> bool:
        now = time.time()
        with self._lock:
            for k in [k for k, exp in self._seen.items() if exp < now]:
                del self._seen[k]
            if key in self._seen:
                return False
            self._seen[key] = expires_at
            return True


# --------------------------------------------------------------------------------------
# Client identity (held by Cortex)
# --------------------------------------------------------------------------------------
@dataclass
class ClientIdentity:
    client_id: str
    private_key: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)

    @property
    def jwk(self) -> Dict[str, str]:
        return public_jwk(self.private_key.public_key())

    @property
    def jkt(self) -> str:
        return jwk_thumbprint(self.jwk)

    def client_assertion(self, token_endpoint: str) -> str:
        now = int(time.time())
        claims = {"iss": self.client_id, "sub": self.client_id, "aud": token_endpoint,
                  "iat": now, "exp": now + 60, "jti": secrets.token_hex(16)}
        return jwt.encode(claims, self.private_key, algorithm="EdDSA")

    def dpop_proof(self, method: str, url: str, access_token: str) -> str:
        claims = {"jti": secrets.token_hex(16), "htm": method.upper(), "htu": url.split("?")[0],
                  "iat": int(time.time()), "ath": b64url(hashlib.sha256(access_token.encode("ascii")).digest())}
        return jwt.encode(claims, self.private_key, algorithm="EdDSA", headers={"typ": "dpop+jwt", "jwk": self.jwk})


# --------------------------------------------------------------------------------------
# Authorisation server (sandbox reference)
# --------------------------------------------------------------------------------------
@dataclass
class RegisteredClient:
    client_id: str
    public_key: Ed25519PublicKey
    allowed_scopes: Sequence[str]
    allowed_sandboxes: Sequence[str]
    tenant: str


class SandboxAuthorizationServer:
    def __init__(self, issuer: str = "https://as.sandbox.s3m.range", *, sandbox_scopes: Mapping[str, Sequence[str]]) -> None:
        self.issuer = issuer
        self.token_endpoint = issuer.rstrip("/") + "/oauth2/token"
        self._key = Ed25519PrivateKey.generate()
        self.public_key = self._key.public_key()
        self._clients: Dict[str, RegisteredClient] = {}
        self._sandbox_scopes = {k: list(v) for k, v in sandbox_scopes.items()}
        self._assertions = ReplayCache()

    def register_client(self, identity_public_key: Ed25519PublicKey, client_id: str, *,
                        scopes: Sequence[str], sandboxes: Sequence[str], tenant: str = "range") -> None:
        self._clients[client_id] = RegisteredClient(client_id, identity_public_key, list(scopes), list(sandboxes), tenant)

    def issue_token(self, *, client_assertion: str, resource: str, sandbox: str,
                    scopes: Sequence[str], dpop_jkt: str) -> Dict[str, Any]:
        unverified = jwt.decode(client_assertion, options={"verify_signature": False})
        client = self._clients.get(str(unverified.get("sub")))
        if client is None:
            raise AuthError("UNAUTHENTICATED", "unknown client")
        try:
            claims = jwt.decode(client_assertion, client.public_key, algorithms=["EdDSA"],
                                audience=self.token_endpoint, issuer=client.client_id, leeway=CLOCK_SKEW)
        except jwt.PyJWTError as exc:
            raise AuthError("UNAUTHENTICATED", f"client assertion rejected: {type(exc).__name__}") from exc
        if claims.get("sub") != client.client_id or not self._assertions.check_and_add(
            f"{client.client_id}:{claims['jti']}", float(claims["exp"]) + CLOCK_SKEW
        ):
            raise AuthError("UNAUTHENTICATED", "client assertion replayed or malformed")
        if sandbox not in client.allowed_sandboxes or sandbox not in self._sandbox_scopes:
            raise AuthError("SANDBOX_DENIED", f"client not enrolled in {sandbox}")
        granted = [s for s in scopes if s in client.allowed_scopes and s in self._sandbox_scopes[sandbox]]
        if not granted:
            raise AuthError("FORBIDDEN_SCOPE", "no requested scope is grantable")
        now = int(time.time())
        token = jwt.encode(
            {"iss": self.issuer, "sub": client.client_id, "client_id": client.client_id, "aud": resource,
             "iat": now, "nbf": now, "exp": now + ACCESS_TOKEN_TTL, "jti": secrets.token_hex(16),
             "scope": " ".join(granted), "sandbox": sandbox, "tenant": client.tenant, "cnf": {"jkt": dpop_jkt}},
            self._key, algorithm="EdDSA", headers={"typ": "at+jwt"},
        )
        return {"access_token": token, "token_type": "DPoP", "expires_in": ACCESS_TOKEN_TTL, "scope": " ".join(granted)}


def verify_access_token(token: str, *, issuer: str, public_key: Ed25519PublicKey, resource: str) -> Dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("typ") != "at+jwt" or header.get("alg") != "EdDSA":
            raise AuthError("UNAUTHENTICATED", "unexpected token type")
        return jwt.decode(token, public_key, algorithms=["EdDSA"], audience=resource, issuer=issuer,
                          leeway=CLOCK_SKEW, options={"require": ["exp", "iat", "jti", "sub", "aud", "cnf"]})
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("TOKEN_EXPIRED", "access token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("UNAUTHENTICATED", f"access token rejected: {type(exc).__name__}") from exc


def verify_dpop(proof: str, *, method: str, url: str, access_token: str, expected_jkt: str, replay: ReplayCache) -> None:
    try:
        header = jwt.get_unverified_header(proof)
        if header.get("typ") != "dpop+jwt" or header.get("alg") != "EdDSA":
            raise AuthError("DPOP_INVALID", "bad DPoP header")
        jwk = header.get("jwk") or {}
        if jwk_thumbprint(jwk) != expected_jkt:
            raise AuthError("DPOP_INVALID", "DPoP key does not match token binding")
        claims = jwt.decode(proof, public_key_from_jwk(jwk), algorithms=["EdDSA"],
                            options={"verify_aud": False, "require": ["jti", "htm", "htu", "iat", "ath"]})
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("DPOP_INVALID", f"DPoP proof rejected: {type(exc).__name__}") from exc
    if claims["htm"] != method.upper() or claims["htu"] != url.split("?")[0]:
        raise AuthError("DPOP_INVALID", "DPoP htm/htu mismatch")
    if abs(time.time() - int(claims["iat"])) > DPOP_MAX_AGE:
        raise AuthError("DPOP_INVALID", "DPoP proof stale")
    if claims["ath"] != b64url(hashlib.sha256(access_token.encode("ascii")).digest()):
        raise AuthError("DPOP_INVALID", "DPoP ath does not match token")
    if not replay.check_and_add(f"{expected_jkt}:{claims['jti']}", time.time() + DPOP_MAX_AGE * 2):
        raise AuthError("DPOP_INVALID", "DPoP proof replayed")


# --------------------------------------------------------------------------------------
# Approval authority (independent of Cortex)
# --------------------------------------------------------------------------------------
class ApprovalAuthority:
    """Mints approval tokens after human device approvals have been verified upstream."""

    def __init__(self, issuer: str = "https://approvals.sandbox.s3m.range") -> None:
        self.issuer = issuer
        self._key = Ed25519PrivateKey.generate()
        self.public_key = self._key.public_key()

    def issue(self, *, client_id: str, resource: str, tool: str, arguments: Mapping[str, Any],
              approval_ids: Iterable[str], ttl_seconds: int = 600) -> str:
        ids = list(approval_ids)
        now = int(time.time())
        return jwt.encode(
            {"iss": self.issuer, "sub": client_id, "aud": resource, "act": tool,
             "args_sha256": args_sha256(arguments), "approvals": len(set(ids)), "approval_ids": ids,
             "iat": now, "exp": now + min(int(ttl_seconds), MAX_APPROVAL_TTL), "jti": secrets.token_hex(16)},
            self._key, algorithm="EdDSA", headers={"typ": "approval+jwt"},
        )


def verify_approval(token: str, *, issuer: str, public_key: Ed25519PublicKey, client_id: str, resource: str,
                    tool: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        if jwt.get_unverified_header(token).get("typ") != "approval+jwt":
            raise AuthError("APPROVAL_INVALID", "not an approval token")
        claims = jwt.decode(token, public_key, algorithms=["EdDSA"], audience=resource, issuer=issuer,
                            leeway=CLOCK_SKEW, options={"require": ["exp", "iat", "jti", "sub", "act", "args_sha256"]})
    except AuthError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("APPROVAL_INVALID", "approval expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("APPROVAL_INVALID", f"approval rejected: {type(exc).__name__}") from exc
    if int(claims["exp"]) - int(claims["iat"]) > MAX_APPROVAL_TTL:
        raise AuthError("APPROVAL_INVALID", "approval lifetime exceeds policy")
    if claims["sub"] != client_id:
        raise AuthError("APPROVAL_INVALID", "approval issued to a different client")
    if claims["act"] != tool:
        raise AuthError("APPROVAL_INVALID", "approval is for a different tool")
    if claims["args_sha256"] != args_sha256(arguments):
        raise AuthError("APPROVAL_INVALID", "approval does not cover these arguments")
    return claims


__all__: List[str] = [
    "ApprovalAuthority", "AuthError", "ClientIdentity", "ReplayCache", "SandboxAuthorizationServer",
    "verify_access_token", "verify_approval", "verify_dpop",
]
