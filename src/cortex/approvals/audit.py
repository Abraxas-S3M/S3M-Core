"""Audit-chain wrapper for every approvals API decision."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.security.crypto import SecureAuditLog


class ApprovalsAudit:
    def __init__(self, log_dir: Optional[str] = None) -> None:
        self._log = SecureAuditLog(log_dir=log_dir or "data/security_audit/approvals")

    def record(self, action: str, details: Dict[str, Any], severity: str = "INFO") -> Dict[str, Any]:
        return self._log.log(action=action, details=details, severity=severity, source="cortex_approvals")
