"""Session token controls for constrained access to credential proxy services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
import threading
from typing import Dict, List

from .vault_client import VaultClient


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class SessionToken:
    """Issued token metadata for one agent session."""

    token: str
    session_id: str
    expires_at: str
    allowed_services: List[str]


@dataclass(slots=True, frozen=True)
class TokenValidation:
    """Validation result returned to gate proxy access checks."""

    valid: bool
    session_id: str
    remaining_ttl: int
    allowed_services: List[str]


class TokenManager:
    """Manages short-lived session tokens that only authorize proxy usage."""

    def __init__(self, vault_client: VaultClient, default_ttl: int = 3600) -> None:
        if vault_client is None:
            raise ValueError("vault_client must be provided")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be positive")
        self.vault_client = vault_client
        self.default_ttl = int(default_ttl)
        self._tokens: Dict[str, SessionToken] = {}
        self._lock = threading.RLock()

    def issue_token(self, session_id: str, allowed_services: List[str], ttl: int = None) -> SessionToken:
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be provided")
        if not allowed_services:
            raise ValueError("allowed_services must be provided")
        effective_ttl = self.default_ttl if ttl is None else int(ttl)
        if effective_ttl <= 0:
            raise ValueError("ttl must be positive")

        cleaned_services = self._normalize_services(allowed_services)
        expires_at = _utc_now() + timedelta(seconds=effective_ttl)
        token = secrets.token_urlsafe(48)
        issued = SessionToken(
            token=token,
            session_id=session_id.strip(),
            expires_at=expires_at.isoformat(),
            allowed_services=cleaned_services,
        )
        with self._lock:
            self._tokens[token] = issued
        return issued

    def validate_token(self, token: str) -> TokenValidation:
        if not token or not token.strip():
            return TokenValidation(valid=False, session_id="", remaining_ttl=0, allowed_services=[])

        with self._lock:
            self._purge_expired_locked()
            issued = self._tokens.get(token.strip())
            if issued is None:
                return TokenValidation(valid=False, session_id="", remaining_ttl=0, allowed_services=[])

        expires_at = datetime.fromisoformat(issued.expires_at)
        remaining = max(0, int((expires_at - _utc_now()).total_seconds()))
        if remaining <= 0:
            self.revoke_token(token)
            return TokenValidation(valid=False, session_id="", remaining_ttl=0, allowed_services=[])
        return TokenValidation(
            valid=True,
            session_id=issued.session_id,
            remaining_ttl=remaining,
            allowed_services=list(issued.allowed_services),
        )

    def revoke_token(self, token: str) -> None:
        if not token or not token.strip():
            raise ValueError("token must be provided")
        with self._lock:
            self._tokens.pop(token.strip(), None)

    def revoke_all_for_session(self, session_id: str) -> None:
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be provided")
        with self._lock:
            # Tactical context: this is the breach-containment kill switch for a compromised session.
            tokens_to_revoke = [
                token for token, issued in self._tokens.items() if issued.session_id == session_id.strip()
            ]
            for token in tokens_to_revoke:
                self._tokens.pop(token, None)

    def _normalize_services(self, allowed_services: List[str]) -> List[str]:
        cleaned: List[str] = []
        for service in allowed_services:
            if not service or not str(service).strip():
                continue
            normalized = str(service).strip()
            if normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            raise ValueError("allowed_services must contain at least one valid service name")
        return cleaned

    def _purge_expired_locked(self) -> None:
        now = _utc_now()
        expired_tokens = []
        for token, issued in self._tokens.items():
            expires_at = datetime.fromisoformat(issued.expires_at)
            if expires_at <= now:
                expired_tokens.append(token)
        for token in expired_tokens:
            self._tokens.pop(token, None)
