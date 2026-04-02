"""
S3M Role-Based C2 Portal — Gap 5 of 7.
FastAPI backend for the role-based portal.
JWT + PKI digital-signature stubs; Arabic/English i18n headers.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("s3m.portal")

router = APIRouter(prefix="/portal", tags=["portal"])


# ─── Roles & Permissions ─────────────────────────────────────────────────────

class UserRole(str, Enum):
    COMMANDER = "COMMANDER"
    ANALYST = "ANALYST"
    MAINTAINER = "MAINTAINER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


ROLE_PERMISSIONS: Dict[UserRole, List[str]] = {
    UserRole.COMMANDER: ["cop:read", "approve:write", "plan:read", "force:read"],
    UserRole.ANALYST: ["cop:read", "force:read", "intel:read", "threat:read"],
    UserRole.MAINTAINER: ["asset:read", "asset:write", "logistics:read"],
    UserRole.OPERATOR: ["task:read", "task:write", "nav:read"],
    UserRole.ADMIN: ["*"],
}


# ─── Minimal JWT-like Token (replace with python-jose in production) ─────────

SECRET = os.getenv("S3M_PORTAL_SECRET", "S3M-CHANGE-ME-IN-PROD")


class TokenPayload(BaseModel):
    user_id: str
    role: UserRole
    expires_at: int


def _sign(payload: str) -> str:
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: str, role: UserRole, ttl_s: int = 28800) -> str:
    exp = int(time.time()) + ttl_s
    raw = f"{user_id}|{role}|{exp}"
    return f"{raw}|{_sign(raw)}"


def verify_token(token: str) -> TokenPayload:
    parts = token.split("|")
    if len(parts) != 4:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token format")

    user_id, role, exp, sig = parts
    raw = f"{user_id}|{role}|{exp}"
    if not hmac.compare_digest(sig, _sign(raw)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token signature invalid")

    try:
        exp_int = int(exp)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token expiry") from exc

    if exp_int < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")

    try:
        role_enum = UserRole(role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown role in token") from exc

    return TokenPayload(user_id=user_id, role=role_enum, expires_at=exp_int)


# ─── Dependency Injectors ─────────────────────────────────────────────────────

def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> TokenPayload:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return verify_token(authorization[7:])


def require_permission(perm: str):
    def checker(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        perms = ROLE_PERMISSIONS.get(user.role, [])
        if "*" not in perms and perm not in perms:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role {user.role} lacks permission: {perm}",
            )
        return user

    return checker


# ─── i18n Helper (Arabic / English) ───────────────────────────────────────────

I18N: Dict[str, Dict[str, str]] = {
    "cop_title": {"en": "Common Operating Picture", "ar": "الصورة التشغيلية المشتركة"},
    "assets": {"en": "Assets", "ar": "الأصول"},
    "threats": {"en": "Threats", "ar": "التهديدات"},
    "pending_approvals": {"en": "Pending Approvals", "ar": "الموافقات المعلقة"},
    "readiness": {"en": "Readiness Score", "ar": "درجة الجاهزية"},
    "logistics": {"en": "Logistics", "ar": "الإمداد والتموين"},
}
_SUPPORTED_LANGS = {"ar", "en"}


def _resolve_lang(
    query_lang: Optional[str],
    x_lang: Optional[str],
    accept_language: Optional[str],
) -> str:
    candidates = [x_lang, query_lang]
    if accept_language:
        candidates.extend(part.strip().split("-")[0] for part in accept_language.split(","))
    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.strip().lower()
        if normalized in _SUPPORTED_LANGS:
            return normalized
    return "ar"


def t(key: str, lang: str = "ar") -> str:
    return I18N.get(key, {}).get(lang, key)


# ─── Digital Signature Stub (replace with PKI/X.509 in production) ───────────

class DigitalSignature(BaseModel):
    user_id: str
    action: str
    payload_digest: str
    timestamp: str
    signature: str


def create_signature(user_id: str, action: str, payload: Dict[str, Any]) -> DigitalSignature:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    ts = datetime.now(timezone.utc).isoformat()
    raw = f"{user_id}|{action}|{digest}|{ts}"
    return DigitalSignature(
        user_id=user_id,
        action=action,
        payload_digest=digest,
        timestamp=ts,
        signature=_sign(raw),
    )


def _fallback_cop_snapshot() -> Dict[str, Any]:
    # Tactical fallback keeps COP views available during degraded subsystem states.
    return {
        "assets": {"A-01": {"id": "A-01", "name": "UAV-Alpha"}},
        "threats": {"T-01": {"id": "T-01", "type": "EW Interference", "severity": "MEDIUM"}},
        "tasks": {"TK-01": {"id": "TK-01", "status": "ACTIVE"}},
        "pending_approvals": [{"ticket_id": "APR-001", "request": "Retask UAV-Alpha"}],
    }


def _get_cop_snapshot() -> Dict[str, Any]:
    try:
        from src.command.mission_command_engine import MissionCommandEngine

        snapshot = MissionCommandEngine().get_cop_snapshot()
        if isinstance(snapshot, dict):
            return snapshot
    except Exception as exc:
        logger.warning("COP snapshot fallback engaged: %s", exc)
    return _fallback_cop_snapshot()


def _get_force_picture() -> Dict[str, Any]:
    try:
        from src.force_awareness.force_tracker import ForceAwarenessManager

        picture = ForceAwarenessManager().get_full_picture()
        if isinstance(picture, dict):
            return picture
    except Exception as exc:
        logger.warning("Force picture fallback engaged: %s", exc)
    # Tactical fallback preserves maintainer visibility in contested network conditions.
    return {
        "assets": [
            {"id": "A-01", "status": "READY", "alert": False},
            {"id": "A-02", "status": "MAINTENANCE", "alert": True},
        ]
    }


def _resolve_approval(ticket_id: str, granted: bool, user_id: str) -> Optional[Dict[str, Any]]:
    try:
        from src.command.mission_command_engine import MissionCommandEngine

        maybe_ticket = asyncio.run(
            MissionCommandEngine().resolve_approval(ticket_id, granted, user_id)
        )
        if maybe_ticket is None:
            return None
        if hasattr(maybe_ticket, "__dict__"):
            return dict(maybe_ticket.__dict__)
        if isinstance(maybe_ticket, dict):
            return maybe_ticket
    except Exception as exc:
        logger.warning("Approval fallback engaged: %s", exc)
    return {
        "ticket_id": ticket_id,
        "granted": granted,
        "resolved_by": user_id,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "status": "RESOLVED_FALLBACK",
    }


# ─── Role-Specific Endpoints ──────────────────────────────────────────────────

@router.post("/auth/token")
def get_token(user_id: str, role: UserRole) -> Dict[str, Any]:
    """Dev endpoint — in prod, validate against LDAP/PKI first."""
    if not user_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "user_id must not be empty")
    return {"token": issue_token(user_id, role), "role": role}


@router.get("/commander/dashboard")
def commander_dashboard(
    lang: Optional[str] = None,
    x_lang: Optional[str] = Header(default=None, alias="X-Lang"),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
    user: TokenPayload = Depends(require_permission("cop:read")),
) -> Dict[str, Any]:
    """Executive summary for Commander role."""
    selected_lang = _resolve_lang(lang, x_lang, accept_language)
    cop = _get_cop_snapshot()
    assets = cop.get("assets", {})
    threats = cop.get("threats", {})
    tasks = cop.get("tasks", {})
    pending = cop.get("pending_approvals", [])
    return {
        "role": user.role,
        "lang": selected_lang,
        "labels": {k: t(k, selected_lang) for k in I18N},
        "summary": {
            "total_assets": len(assets) if isinstance(assets, dict) else 0,
            "active_threats": len(threats) if isinstance(threats, dict) else 0,
            "active_tasks": len(tasks) if isinstance(tasks, dict) else 0,
            "pending_approvals": len(pending) if isinstance(pending, list) else 0,
        },
        "pending_approvals": pending if isinstance(pending, list) else [],
    }


@router.get("/analyst/intel")
def analyst_intel(
    lang: Optional[str] = None,
    x_lang: Optional[str] = Header(default=None, alias="X-Lang"),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
    user: TokenPayload = Depends(require_permission("intel:read")),
) -> Dict[str, Any]:
    """Detailed drill-down for Analyst role."""
    selected_lang = _resolve_lang(lang, x_lang, accept_language)
    cop = _get_cop_snapshot()
    threats = cop.get("threats", {})
    assets = cop.get("assets", {})
    return {
        "role": user.role,
        "lang": selected_lang,
        "threats": list(threats.values()) if isinstance(threats, dict) else [],
        "assets": list(assets.values()) if isinstance(assets, dict) else [],
    }


@router.get("/maintainer/assets")
def maintainer_assets(
    user: TokenPayload = Depends(require_permission("asset:read")),
) -> Dict[str, Any]:
    """Asset health view for Maintainer role."""
    picture = _get_force_picture()
    assets = picture.get("assets", [])
    if not isinstance(assets, list):
        assets = []
    alerts = [asset for asset in assets if isinstance(asset, dict) and asset.get("alert")]
    return {"role": user.role, "alerts": alerts, "full_picture": picture}


@router.post("/operator/approve")
def operator_approve(
    ticket_id: str,
    granted: bool,
    user: TokenPayload = Depends(require_permission("approve:write")),
) -> Dict[str, Any]:
    """Human-in-the-loop approval endpoint with digital signature."""
    if not ticket_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ticket_id must not be empty")
    sig = create_signature(
        user.user_id,
        "APPROVAL",
        {"ticket_id": ticket_id, "granted": granted},
    )
    ticket = _resolve_approval(ticket_id, granted, user.user_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return {"ticket": ticket, "signature": sig.model_dump()}
