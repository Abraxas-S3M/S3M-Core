"""Shared adapter primitives for offline-first SOC platform integration."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib import error, request


class IRPlatformAdapter:
    """Base class with safe HTTP and resilient outbox behavior for air-gapped SOC."""

    def __init__(self, url: str, api_key: Optional[str], outbox_dir: str) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.outbox_dir = outbox_dir
        os.makedirs(self.outbox_dir, exist_ok=True)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        timeout: float = 1.5,
    ) -> Dict[str, Any]:
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.url}{path}",
            data=data,
            headers=self._headers(),
            method=method.upper(),
        )
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8") if response.readable() else ""
            if not body:
                return {"status": response.status}
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"status": response.status, "raw": body}

    def _safe_request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        timeout: float = 1.5,
    ) -> Optional[Dict[str, Any]]:
        try:
            return self._request(method=method, path=path, payload=payload, timeout=timeout)
        except (error.URLError, error.HTTPError, TimeoutError, ConnectionError, OSError):
            return None

    def _write_outbox(self, operation: str, payload: dict) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        item = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "url": self.url,
            "payload": payload,
        }
        filename = os.path.join(self.outbox_dir, f"{timestamp}_{operation}.json")
        with open(filename, "w", encoding="utf-8") as handle:
            json.dump(item, handle, indent=2)

    def _read_outbox_files(self) -> list[str]:
        files = [
            os.path.join(self.outbox_dir, name)
            for name in os.listdir(self.outbox_dir)
            if name.endswith(".json")
        ]
        files.sort()
        return files

