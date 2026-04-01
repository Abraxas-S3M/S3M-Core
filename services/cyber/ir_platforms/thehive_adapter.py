"""TheHive adapter with offline outbox support for tactical SOC continuity."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.cyber.ir_platforms.base import IRPlatformAdapter
from services.cyber.models import CaseSeverity, IncidentCase, Observable


class TheHiveAdapter(IRPlatformAdapter):
    """Bridge incident cases to TheHive while remaining safe when offline."""

    def __init__(self, url: str = "http://localhost:9000", api_key: str = None) -> None:
        super().__init__(url=url, api_key=api_key, outbox_dir="data/cyber/thehive_outbox")

    def connect(self) -> bool:
        return self._safe_request("GET", "/api/status") is not None

    def _severity_to_thehive(self, severity: CaseSeverity) -> int:
        mapped = {
            CaseSeverity.LOW: 1,
            CaseSeverity.MEDIUM: 2,
            CaseSeverity.HIGH: 3,
            CaseSeverity.CRITICAL: 4,
            CaseSeverity.INFORMATIONAL: 1,
        }
        return mapped[severity]

    def _offline(self, operation: str, payload: dict) -> dict:
        self._write_outbox(operation, payload)
        return {"error": "TheHive unavailable", "status": "queued_offline"}

    def create_alert(self, case: IncidentCase) -> dict:
        payload = {
            "title": case.title,
            "description": case.description,
            "severity": self._severity_to_thehive(case.severity),
            "tags": list(case.tags),
            "source": "S3M_SOC",
            "sourceRef": case.case_id,
            "artifacts": list(case.observables),
            "tlp": 2,
        }
        response = self._safe_request("POST", "/api/v1/alert", payload)
        if response is None:
            return self._offline("create_alert", payload)
        return {"thehive_id": str(response.get("id", response.get("_id", str(uuid4())))), "status": "created"}

    def create_case(self, case: IncidentCase) -> dict:
        payload = {
            "title": case.title,
            "description": case.description,
            "severity": self._severity_to_thehive(case.severity),
            "tags": list(case.tags),
            "flag": case.severity in {CaseSeverity.HIGH, CaseSeverity.CRITICAL},
            "tlp": 2,
            "pap": 2,
            "customFields": {
                "s3m_case_id": {"string": case.case_id},
                "classification": {"string": case.classification},
            },
        }
        response = self._safe_request("POST", "/api/v1/case", payload)
        if response is None:
            return self._offline("create_case", payload)
        return {"thehive_id": str(response.get("id", response.get("_id", str(uuid4())))), "status": "created"}

    def update_case(self, thehive_id: str, updates: dict) -> dict:
        response = self._safe_request("PATCH", f"/api/v1/case/{thehive_id}", updates)
        if response is None:
            return self._offline("update_case", {"thehive_id": thehive_id, "updates": updates})
        return {"thehive_id": thehive_id, "status": "updated"}

    def add_observable(self, thehive_id: str, observable: Observable) -> dict:
        payload = {
            "dataType": observable.observable_type.value.lower(),
            "data": observable.value,
            "tags": list(observable.tags),
            "tlp": {"WHITE": 0, "GREEN": 1, "AMBER": 2, "RED": 3}.get(observable.tlp, 2),
        }
        response = self._safe_request("POST", f"/api/v1/case/{thehive_id}/observable", payload)
        if response is None:
            return self._offline("add_observable", {"thehive_id": thehive_id, "payload": payload})
        return {"status": "added", "observable_id": response.get("id", observable.observable_id)}

    def get_case(self, thehive_id: str) -> dict:
        response = self._safe_request("GET", f"/api/v1/case/{thehive_id}")
        if response is None:
            return self._offline("get_case", {"thehive_id": thehive_id})
        return response

    def search_cases(self, query: dict) -> List[dict]:
        response = self._safe_request("POST", "/api/v1/query", query)
        if response is None:
            self._write_outbox("search_cases", query)
            return []
        if isinstance(response, list):
            return response
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return response["data"]
        return []

    def get_outbox(self) -> List[dict]:
        items: List[dict] = []
        for filepath in self._read_outbox_files():
            try:
                with open(filepath, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            payload["_filepath"] = filepath
            items.append(payload)
        return items

    def flush_outbox(self) -> int:
        success_count = 0
        if not self.connect():
            return 0
        for item in self.get_outbox():
            op = item.get("operation")
            payload = item.get("payload", {})
            ok = False
            if op == "create_alert":
                ok = self._safe_request("POST", "/api/v1/alert", payload) is not None
            elif op == "create_case":
                ok = self._safe_request("POST", "/api/v1/case", payload) is not None
            elif op == "update_case":
                th_id = payload.get("thehive_id", "")
                updates = payload.get("updates", {})
                ok = self._safe_request("PATCH", f"/api/v1/case/{th_id}", updates) is not None
            elif op == "add_observable":
                th_id = payload.get("thehive_id", "")
                body = payload.get("payload", {})
                ok = self._safe_request("POST", f"/api/v1/case/{th_id}/observable", body) is not None
            else:
                ok = True
            if ok:
                success_count += 1
                filepath = item.get("_filepath")
                if isinstance(filepath, str) and os.path.exists(filepath):
                    os.remove(filepath)
        return success_count
