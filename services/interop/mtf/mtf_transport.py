"""Online/offline transport adapter for APP-11 XML-MTF payload delivery."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


class MTFTransport:
    """Posts XML-MTF to a gateway, or queues locally when disconnected."""

    def __init__(self, gateway_url: str | None = None) -> None:
        self.gateway_url = gateway_url
        self.connected = False
        self.outbox_dir = Path("data/interop/mtf_outbox")
        self.inbox_dir = Path("data/interop/mtf_inbox")
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def connect(self, url: str | None) -> bool:
        if url:
            self.gateway_url = url
        if not self.gateway_url:
            self.connected = False
            return False

        status_url = f"{self.gateway_url.rstrip('/')}/status"
        try:
            with urllib.request.urlopen(status_url, timeout=2) as resp:
                self.connected = 200 <= resp.status < 300
                return self.connected
        except (urllib.error.URLError, TimeoutError, ValueError):
            self.connected = False
            return False

    def disconnect(self) -> None:
        self.connected = False

    def push_message(
        self,
        xml_str: str,
        message_type: str = "INTSUM",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.connected and self.gateway_url:
            endpoint = f"{self.gateway_url.rstrip('/')}/{message_type}"
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

        queued = self._write_outbox(xml_str=xml_str, message_type=message_type, metadata=metadata)
        return {"status": "queued_offline", **queued}

    def pull_messages(self, message_type: str | None = None) -> list[str]:
        if self.connected and self.gateway_url:
            suffix = f"?type={message_type}" if message_type else ""
            endpoint = f"{self.gateway_url.rstrip('/')}/messages{suffix}"
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

        rows: list[str] = []
        for path in sorted(self.inbox_dir.glob("*.xml")):
            rows.append(path.read_text(encoding="utf-8"))
        return rows

    def list_outbox(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.outbox_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            rows.append(payload)
        return rows

    def get_server_status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "gateway_url": self.gateway_url,
            "offline_outbox_count": len(list(self.outbox_dir.glob("*.json"))),
            "offline_inbox_count": len(list(self.inbox_dir.glob("*.xml"))),
        }

    def _write_outbox(
        self,
        xml_str: str,
        message_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message_id = f"{message_type.lower()}-{uuid4().hex[:10]}"
        queued_at = datetime.now(timezone.utc).isoformat()
        xml_path = self.outbox_dir / f"{message_id}.xml"
        meta_path = self.outbox_dir / f"{message_id}.json"

        xml_path.write_text(xml_str, encoding="utf-8")
        payload = {
            "message_id": message_id,
            "message_type": message_type,
            "queued_at": queued_at,
            "xml_path": str(xml_path),
            "metadata_path": str(meta_path),
            "metadata": dict(metadata or {}),
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload
