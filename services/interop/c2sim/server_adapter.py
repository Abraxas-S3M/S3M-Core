"""C2SIM server connector with offline inbox/outbox persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
from typing import List, Optional
from uuid import uuid4


class C2SIMServerAdapter:
    """Connects to C2SIM REST endpoints with resilient offline fallback."""

    def __init__(self, server_url: str = None):
        self.server_url = server_url
        self.connected = False
        self.outbox_dir = Path("data/interop/c2sim_outbox")
        self.inbox_dir = Path("data/interop/c2sim_inbox")
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def connect(self, url: str) -> bool:
        if url:
            self.server_url = url
        if not self.server_url:
            self.connected = False
            return False
        status_url = f"{self.server_url.rstrip('/')}/C2SIMServer/status"
        try:
            with urllib.request.urlopen(status_url, timeout=2) as resp:
                self.connected = 200 <= resp.status < 300
                return self.connected
        except (urllib.error.URLError, TimeoutError, ValueError):
            self.connected = False
            return False

    def disconnect(self):
        self.connected = False

    def _write_outbox(self, xml_str: str, message_type: str) -> dict:
        message_id = f"{message_type.lower()}-{uuid4().hex[:10]}"
        payload = {
            "message_id": message_id,
            "message_type": message_type,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "xml": xml_str,
        }
        path = self.outbox_dir / f"{message_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def push_message(self, xml_str: str, message_type: str = "Order") -> dict:
        if self.connected and self.server_url:
            endpoint = f"{self.server_url.rstrip('/')}/C2SIMServer/{message_type}"
            req = urllib.request.Request(
                endpoint,
                data=xml_str.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=3) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                    return {
                        "status": "sent",
                        "message_type": message_type,
                        "http_status": resp.status,
                        "response": body,
                    }
            except (urllib.error.URLError, TimeoutError, ValueError):
                self.connected = False
        queued = self._write_outbox(xml_str, message_type)
        return {"status": "queued_offline", **queued}

    def pull_messages(self, message_type: str = None, since: str = None) -> List[str]:
        if self.connected and self.server_url:
            q = []
            if message_type:
                q.append(f"type={message_type}")
            if since:
                q.append(f"since={since}")
            suffix = f"?{'&'.join(q)}" if q else ""
            endpoint = f"{self.server_url.rstrip('/')}/C2SIMServer/messages{suffix}"
            try:
                with urllib.request.urlopen(endpoint, timeout=3) as resp:
                    payload = resp.read().decode("utf-8", errors="ignore")
                if payload.strip().startswith("["):
                    rows = json.loads(payload)
                    return [str(item) for item in rows if isinstance(item, str)]
                if payload.strip():
                    return [payload]
                return []
            except Exception:
                self.connected = False

        rows: List[str] = []
        for path in sorted(self.inbox_dir.glob("*.xml")):
            rows.append(path.read_text(encoding="utf-8"))
        return rows

    def get_server_status(self) -> dict:
        return {
            "connected": self.connected,
            "server_url": self.server_url,
            "offline_outbox_count": len(list(self.outbox_dir.glob("*.json"))),
            "offline_inbox_count": len(list(self.inbox_dir.glob("*.xml"))),
        }

    def list_sessions(self) -> List[dict]:
        if self.connected and self.server_url:
            endpoint = f"{self.server_url.rstrip('/')}/C2SIMServer/sessions"
            try:
                with urllib.request.urlopen(endpoint, timeout=3) as resp:
                    payload = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(payload)
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            except Exception:
                self.connected = False
        return []
