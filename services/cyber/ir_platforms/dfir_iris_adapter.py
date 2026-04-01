"""DFIR-IRIS adapter with offline outbox continuity for forensic operations."""

from __future__ import annotations

from typing import List
from uuid import uuid4

from services.cyber.ir_platforms.base import IRPlatformAdapter
from services.cyber.models import IncidentCase, Observable


class DFIRIRISAdapter(IRPlatformAdapter):
    """Interfaces with DFIR-IRIS while preserving operations in disconnected mode."""

    def __init__(self, url: str = "http://localhost:8000", api_key: str = None) -> None:
        super().__init__(url=url, api_key=api_key, outbox_dir="data/cyber/dfir_iris_outbox")

    def connect(self) -> bool:
        return self._safe_request("GET", "/api/health") is not None

    def create_case(self, case: IncidentCase) -> dict:
        payload = {
            "title": case.title,
            "description": case.description,
            "severity": case.severity.value,
            "classification": case.classification,
            "external_ref": case.case_id,
        }
        response = self._safe_request("POST", "/api/cases", payload)
        if response is None:
            self._write_outbox("create_case", payload)
            return {"error": "DFIR-IRIS unavailable", "status": "queued_offline"}
        return {"case_id": str(response.get("id", response.get("case_id", str(uuid4())))), "status": "created"}

    def add_evidence(self, case_id: str, evidence: dict) -> dict:
        response = self._safe_request("POST", f"/api/cases/{case_id}/evidence", evidence)
        if response is None:
            self._write_outbox("add_evidence", {"case_id": case_id, "evidence": evidence})
            return {"error": "DFIR-IRIS unavailable", "status": "queued_offline"}
        return {"status": "added"}

    def add_ioc(self, case_id: str, observable: Observable) -> dict:
        payload = {"type": observable.observable_type.value, "value": observable.value, "tags": observable.tags}
        response = self._safe_request("POST", f"/api/cases/{case_id}/iocs", payload)
        if response is None:
            self._write_outbox("add_ioc", {"case_id": case_id, "payload": payload})
            return {"error": "DFIR-IRIS unavailable", "status": "queued_offline"}
        return {"status": "added"}

    def get_timeline(self, case_id: str) -> List[dict]:
        response = self._safe_request("GET", f"/api/cases/{case_id}/timeline")
        if response is None:
            self._write_outbox("get_timeline", {"case_id": case_id})
            return []
        if isinstance(response, list):
            return response
        if isinstance(response, dict) and isinstance(response.get("timeline"), list):
            return response["timeline"]
        return []
