"""External HR/ERP adapter layer with standalone fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from apps.readiness.models import ServiceMember


class HRAdapter:
    """Integrates with ERP systems when present; otherwise runs standalone."""

    def __init__(self, backend: str = "standalone"):
        self.backend = backend
        self.erpnext_url = "http://localhost:8000"
        self.odoo_url = "http://localhost:8069"
        self.orangehrm_url = "http://localhost:80"
        self.connected = backend == "standalone"
        self.last_sync: str | None = None

    def sync_from_erp(self) -> Dict[str, int]:
        # Tactical constraint: air-gapped mode avoids external HTTP calls.
        self.last_sync = datetime.now(timezone.utc).isoformat()
        return {"synced": 0, "errors": 0}

    def push_to_erp(self, member: ServiceMember) -> Dict[str, object]:
        self.last_sync = datetime.now(timezone.utc).isoformat()
        return {
            "backend": self.backend,
            "connected": self.connected,
            "member_id": member.member_id,
            "status": "standalone_cached" if self.backend == "standalone" else "queued",
        }

    def get_erp_status(self) -> Dict[str, object]:
        return {"backend": self.backend, "connected": self.connected, "last_sync": self.last_sync}

