"""Coalition identity federation scaffolding for FMN interoperability.

This module provides structural validation and authorization hooks for tactical
coalition identity workflows without implementing real cryptographic trust logic.
"""

from __future__ import annotations

import hashlib
import ssl
from datetime import datetime, timezone
from typing import Any

from services.interop.fmn_security.security_labels import (
    classify_rank,
    normalize_classification,
)


def _validate_nation(nation: str) -> str:
    code = str(nation or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("nation must be ISO 3166 alpha-3")
    return code


def _clearance_rank(clearance: str) -> int:
    return classify_rank(clearance)


class CoalitionIdentityProvider:
    """Identity registry and policy checks for coalition users."""

    _VALID_TOKEN_TYPES = {"SAML", "OAUTH"}
    _VALID_TOKEN_STATUS = {"VALID", "EXPIRED", "REVOKED"}

    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}

    def register_coalition_user(
        self,
        user_id: str,
        nation: str,
        clearance: str,
        roles: list[str],
    ) -> dict[str, Any]:
        """Register coalition user metadata for mission federation workflows."""
        normalized_user = str(user_id or "").strip()
        if not normalized_user:
            raise ValueError("user_id is required")

        normalized_nation = _validate_nation(nation)
        if not isinstance(roles, list) or not roles:
            raise ValueError("roles must be a non-empty list")
        normalized_roles = [str(role).strip() for role in roles if str(role).strip()]
        if not normalized_roles:
            raise ValueError("roles must contain at least one non-empty value")

        record = {
            "user_id": normalized_user,
            "nation": normalized_nation,
            "clearance": normalize_classification(clearance),
            "roles": normalized_roles,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._users[normalized_user] = record
        return dict(record)

    def authenticate_certificate(self, cert_pem: str) -> dict[str, Any]:
        """Parse X.509 PEM structure and extract deterministic identity fields.

        Tactical context: this is a framework-level parser for FMN interop tests.
        It intentionally avoids live PKI chain validation or signature checks.
        """
        cert_text = str(cert_pem or "").strip()
        if "BEGIN CERTIFICATE" not in cert_text or "END CERTIFICATE" not in cert_text:
            raise ValueError("cert_pem must contain a complete PEM certificate block")

        try:
            der_bytes = ssl.PEM_cert_to_DER_cert(cert_text)
        except Exception as exc:
            raise ValueError("invalid PEM certificate structure") from exc

        fingerprint = hashlib.sha256(der_bytes).hexdigest()
        return {
            "user_id": f"cert-{fingerprint[:12]}",
            "auth_method": "x509_certificate",
            "certificate_fingerprint_sha256": fingerprint,
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate token shape for SAML/OAuth federation plumbing.

        Accepted format:
            TYPE|user_id|nation|clearance|status
        Example:
            SAML|falcon-01|SAU|NATO SECRET|VALID
        """
        token_text = str(token or "").strip()
        if not token_text:
            raise ValueError("token is required")

        parts = [part.strip() for part in token_text.split("|")]
        if len(parts) != 5:
            raise ValueError("token must follow TYPE|user_id|nation|clearance|status format")

        token_type, user_id, nation, clearance, status = parts
        token_type = token_type.upper()
        status = status.upper()

        if token_type not in self._VALID_TOKEN_TYPES:
            raise ValueError("token type must be SAML or OAUTH")
        if status not in self._VALID_TOKEN_STATUS:
            raise ValueError("token status must be VALID, EXPIRED, or REVOKED")

        normalized = {
            "token_type": token_type,
            "user_id": user_id,
            "nation": _validate_nation(nation),
            "clearance": normalize_classification(clearance),
            "status": status,
            "token_valid": status == "VALID",
        }
        return normalized

    def check_authorization(self, user: dict[str, Any], required_clearance: str, operation: str) -> bool:
        """Authorize operation by role scope and clearance threshold."""
        if not isinstance(user, dict):
            return False

        operation_scope = str(operation or "").strip().lower()
        if not operation_scope:
            return False

        roles_raw = user.get("roles", [])
        if not isinstance(roles_raw, list):
            return False
        role_set = {str(role).strip().lower() for role in roles_raw if str(role).strip()}
        if not role_set:
            return False

        if not (
            "admin" in role_set
            or "interop_operator" in role_set
            or operation_scope in role_set
        ):
            return False

        try:
            user_rank = _clearance_rank(str(user.get("clearance", "")))
            required_rank = _clearance_rank(required_clearance)
        except ValueError:
            return False
        return user_rank >= required_rank

    def get_coalition_roster(self) -> list[dict[str, Any]]:
        """Return all registered coalition users sorted by user ID."""
        return [dict(self._users[key]) for key in sorted(self._users)]
