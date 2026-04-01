"""Graylog adapter with local buffering for air-gapped SOC resilience."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List
from urllib import error, request


class GraylogAdapter:
    """Sends and queries tactical logs in Graylog with offline buffer fallback."""

    def __init__(self, url: str = "http://localhost:9000/api", username: str = "admin", password: str = None) -> None:
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.buffer_dir = "data/cyber/graylog_buffer"
        os.makedirs(self.buffer_dir, exist_ok=True)

    def connect(self) -> bool:
        req = request.Request(f"{self.url}/system", method="GET")
        try:
            with request.urlopen(req, timeout=1.5):
                return True
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            return False

    def _save_buffer(self, message: dict) -> None:
        filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ.jsonl")
        path = os.path.join(self.buffer_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(message) + "\n")

    def _normalize_level(self, level: object) -> int:
        if isinstance(level, int):
            return max(0, min(level, 7))
        text = str(level).upper().strip()
        mapping = {
            "CRITICAL": 2,
            "HIGH": 3,
            "MEDIUM": 4,
            "LOW": 5,
            "INFORMATIONAL": 6,
            "INFO": 6,
        }
        return mapping.get(text, 6)

    def send_message(self, message: dict, stream: str = "s3m-events") -> bool:
        gelf = {
            "version": "1.1",
            "host": "s3m_soc",
            "short_message": str(message.get("title", message.get("short_message", "S3M Event"))),
            "full_message": str(message.get("description", message.get("full_message", ""))),
            "level": self._normalize_level(message.get("level", 6)),
            "_threat_level": str(message.get("threat_level", message.get("level_name", "INFO"))),
            "_category": str(message.get("category", "CYBER")),
            "_source": str(message.get("source", "S3M")),
            "_stream": stream,
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        payload = json.dumps(gelf).encode("utf-8")
        req = request.Request(
            f"{self.url}/gelf",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=1.5):
                return True
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            self._save_buffer(gelf)
            return False

    def send_batch(self, messages: List[dict]) -> dict:
        success = 0
        for message in messages:
            if self.send_message(message):
                success += 1
        return {"sent": success, "failed": len(messages) - success, "total": len(messages)}

    def search(self, query: str, timerange_seconds: int = 3600, limit: int = 50) -> List[dict]:
        endpoint = (
            f"{self.url}/search/universal/relative"
            f"?query={query}&range={int(timerange_seconds)}&limit={int(limit)}"
        )
        req = request.Request(endpoint, method="GET")
        try:
            with request.urlopen(req, timeout=2.0) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("messages", []) if isinstance(data, dict) else []
        except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return []

    def get_streams(self) -> List[dict]:
        req = request.Request(f"{self.url}/streams", method="GET")
        try:
            with request.urlopen(req, timeout=2.0) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("streams", []) if isinstance(data, dict) else []
        except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return []
