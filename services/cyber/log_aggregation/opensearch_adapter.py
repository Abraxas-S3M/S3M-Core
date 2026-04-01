"""OpenSearch adapter with local buffering for disconnected deployments."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib import request


class OpenSearchAdapter:
    """Indexes SOC logs into OpenSearch with offline queue fallback."""

    def __init__(self, url: str = "http://localhost:9200", username: str = None, password: str = None) -> None:
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self._buffer_dir = "data/cyber/opensearch_buffer"
        os.makedirs(self._buffer_dir, exist_ok=True)

    def connect(self) -> bool:
        try:
            req = request.Request(f"{self.url}/_cluster/health", method="GET")
            with request.urlopen(req, timeout=1.5):
                return True
        except Exception:
            return False

    def _buffer(self, operation: str, payload: dict) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = os.path.join(self._buffer_dir, f"{ts}_{operation}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def index_event(self, event: dict, index: str = "s3m-threats") -> bool:
        doc_id = event.get("id", datetime.now(timezone.utc).strftime("%s%f"))
        endpoint = f"{self.url}/{index}/_doc/{doc_id}"
        payload = dict(event)
        level_value = payload.get("level")
        if isinstance(level_value, str):
            level_map = {"INFO": 6, "LOW": 5, "MEDIUM": 4, "HIGH": 3, "CRITICAL": 2}
            payload["level_name"] = level_value.upper()
            payload["level"] = level_map.get(level_value.upper(), 6)
        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="PUT")
            with request.urlopen(req, timeout=1.5):
                return True
        except Exception:
            self._buffer("index_event", {"index": index, "event": payload})
            return False

    def index_batch(self, events: List[dict], index: str = "s3m-threats") -> dict:
        sent = 0
        for event in events:
            if self.index_event(event, index=index):
                sent += 1
        return {"sent": sent, "total": len(events), "failed": len(events) - sent}

    def search(self, query: str, index: str = "s3m-threats", size: int = 50) -> List[dict]:
        body = {"query": {"match": {"_all": query}}, "size": size}
        endpoint = f"{self.url}/{index}/_search"
        try:
            data = json.dumps(body).encode("utf-8")
            req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with request.urlopen(req, timeout=2.0) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            hits = parsed.get("hits", {}).get("hits", [])
            return [hit.get("_source", {}) for hit in hits if isinstance(hit, dict)]
        except Exception:
            return []

    def create_index(self, index: str, mappings: dict = None) -> bool:
        payload = mappings or {}
        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                f"{self.url}/{index}",
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with request.urlopen(req, timeout=2.0):
                return True
        except Exception:
            self._buffer("create_index", {"index": index, "mappings": payload})
            return False

    def get_indices(self) -> List[dict]:
        try:
            req = request.Request(f"{self.url}/_cat/indices?format=json", method="GET")
            with request.urlopen(req, timeout=2.0) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
