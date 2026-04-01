"""MISP adapter with air-gapped-safe outbox behavior."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from io import StringIO
from typing import Dict, List, Optional

from services.cyber.ir_platforms.base import IRPlatformAdapter
from services.cyber.models import IncidentCase, Observable, ObservableType


class MISPAdapter(IRPlatformAdapter):
    """Shares and queries IOCs through MISP, or queues safely when offline."""

    def __init__(self, url: str = "http://localhost:8080", api_key: str = None) -> None:
        super().__init__(url=url, api_key=api_key, outbox_dir="data/cyber/misp_outbox")
        self._case_registry: Dict[str, IncidentCase] = {}

    def connect(self) -> bool:
        return self._safe_request("GET", "/servers/getVersion") is not None

    def _observable_to_attribute(self, observable: Observable) -> dict:
        type_map = {
            ObservableType.IP_ADDRESS: "ip-src",
            ObservableType.DOMAIN: "domain",
            ObservableType.FILE_HASH_MD5: "md5",
            ObservableType.FILE_HASH_SHA256: "sha256",
            ObservableType.URL: "url",
            ObservableType.EMAIL: "email-src",
        }
        attribute_type = type_map.get(observable.observable_type, "text")
        tlp = "AMBER"
        for tag in observable.tags:
            if str(tag).upper().startswith("TLP:"):
                tlp = str(tag).split(":", 1)[1].upper()
                break
        return {
            "type": attribute_type,
            "value": observable.value,
            "category": "Network activity",
            "to_ids": True,
            "comment": f"S3M case {observable.source_case_id}",
            "Tag": [{"name": f"TLP:{tlp}"}],
        }

    def create_event(self, case: IncidentCase) -> dict:
        self._case_registry[case.case_id] = case
        attributes = []
        for obs in case.observables:
            observable = Observable(
                observable_id=str(obs.get("observable_id", "")),
                observable_type=ObservableType.from_value(str(obs.get("observable_type", "IP_ADDRESS"))),
                value=str(obs.get("value", "")),
                source_case_id=case.case_id,
                tags=list(obs.get("tags", [])),
                tlp=str(obs.get("tlp", "AMBER")),
            )
            attributes.append(self._observable_to_attribute(observable))
        payload = {
            "Event": {
                "info": f"S3M SOC Incident {case.case_id}: {case.title}",
                "analysis": 0,
                "threat_level_id": 2 if case.severity.value in {"HIGH", "CRITICAL"} else 3,
                "distribution": 0,
                "date": datetime.now(timezone.utc).date().isoformat(),
                "Attribute": attributes,
                "Tag": [{"name": "source:S3M"}, {"name": f"classification:{case.classification}"}],
            }
        }
        response = self._safe_request("POST", "/events", payload)
        if response is None:
            self._write_outbox("create_event", payload)
            return {"error": "MISP unavailable", "status": "queued_offline"}
        event_id = str(response.get("Event", {}).get("id", response.get("id", case.case_id)))
        return {"misp_event_id": event_id, "status": "created"}

    def add_attribute(self, misp_event_id: str, observable: Observable) -> dict:
        payload = {"Attribute": self._observable_to_attribute(observable)}
        response = self._safe_request("POST", f"/attributes/add/{misp_event_id}", payload)
        if response is None:
            self._write_outbox("add_attribute", {"misp_event_id": misp_event_id, "payload": payload})
            return {"error": "MISP unavailable", "status": "queued_offline"}
        return {"status": "added", "attribute_id": response.get("Attribute", {}).get("id", observable.observable_id)}

    def search_attributes(self, value: str) -> List[dict]:
        payload = {"value": value}
        response = self._safe_request("POST", "/attributes/restSearch", payload)
        if response is None:
            self._write_outbox("search_attributes", payload)
            return []
        if isinstance(response, dict):
            attrs = response.get("response", {}).get("Attribute", [])
            if isinstance(attrs, list):
                return attrs
        return []

    def get_threat_level(self, observable_value: str) -> dict:
        results = self.search_attributes(observable_value)
        if not results:
            return {"found": False, "events_count": 0, "threat_level": "unknown", "tags": []}
        tags: List[str] = []
        for item in results:
            for tag in item.get("Tag", []):
                if isinstance(tag, dict):
                    tags.append(str(tag.get("name", "")))
        return {
            "found": True,
            "events_count": len(results),
            "threat_level": "high" if len(results) >= 3 else "medium",
            "tags": tags,
        }

    def export_iocs(self, case_id: str, format: str = "csv") -> str:
        case = self._case_registry.get(case_id)
        if case is None:
            raise ValueError(f"Case not found for IOC export: {case_id}")
        rows = []
        for obs in case.observables:
            rows.append(
                {
                    "observable_id": obs.get("observable_id"),
                    "type": obs.get("observable_type"),
                    "value": obs.get("value"),
                    "tlp": obs.get("tlp", "AMBER"),
                }
            )
        fmt = str(format).lower()
        if fmt == "json":
            return json.dumps(rows, indent=2)
        if fmt != "csv":
            raise ValueError("format must be csv or json")
        sio = StringIO()
        writer = csv.DictWriter(sio, fieldnames=["observable_id", "type", "value", "tlp"])
        writer.writeheader()
        writer.writerows(rows)
        return sio.getvalue()
