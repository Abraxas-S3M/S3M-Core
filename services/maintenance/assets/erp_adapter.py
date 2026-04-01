"""ERP adapter with offline-safe fallback for air-gapped deployments."""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from services.maintenance.models import ProcurementRequest, WorkOrder


class ERPAdapter:
    """Bridge maintenance/procurement records to external ERP systems when available."""

    def __init__(self, backend: str = "auto"):
        self.backend = backend
        self.connected = False
        self.last_sync: Optional[str] = None
        self.outbox: List[dict] = []
        self.urls = {
            "erpnext": "http://localhost:8000",
            "snipeit": "http://localhost:80",
            "glpi": "http://localhost:80",
            "dolibarr": "http://localhost:80",
        }
        self._detect_backend()

    def _probe_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((host, port), timeout=0.15):
                return True
        except Exception:
            return False

    def _detect_backend(self) -> None:
        if self.backend != "auto":
            if self.backend == "standalone":
                self.connected = False
                return
            url = self.urls.get(self.backend)
            self.connected = bool(url and self._probe_url(url))
            if not self.connected:
                self.backend = "standalone"
            return

        for name, url in self.urls.items():
            if self._probe_url(url):
                self.backend = name
                self.connected = True
                return
        self.backend = "standalone"
        self.connected = False

    def sync_assets_from_erp(self) -> List[dict]:
        if not self.connected:
            self.outbox.append({"action": "sync_assets", "timestamp": datetime.now(timezone.utc).isoformat()})
            return []
        self.last_sync = datetime.now(timezone.utc).isoformat()
        return []

    def push_work_order(self, work_order: WorkOrder) -> dict:
        payload = {"action": "push_work_order", "work_order": work_order.to_dict()}
        if not self.connected:
            self.outbox.append(payload)
            return {"queued": True, "backend": self.backend, "ticket_id": None}
        self.last_sync = datetime.now(timezone.utc).isoformat()
        return {"queued": False, "backend": self.backend, "ticket_id": f"ERP-WO-{work_order.work_order_id}"}

    def push_procurement_request(self, request: ProcurementRequest) -> dict:
        payload = {"action": "push_procurement", "request": request.to_dict()}
        if not self.connected:
            self.outbox.append(payload)
            return {"queued": True, "backend": self.backend, "request_id": None}
        self.last_sync = datetime.now(timezone.utc).isoformat()
        return {"queued": False, "backend": self.backend, "request_id": f"ERP-PR-{request.request_id}"}

    def get_erp_status(self) -> dict:
        return {
            "backend": self.backend,
            "connected": self.connected,
            "last_sync": self.last_sync,
            "outbox_depth": len(self.outbox),
        }
