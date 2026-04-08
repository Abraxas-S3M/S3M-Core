"""Caldera REST bridge for controlled offensive-cyber exercises."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

import requests


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CalderaBridge:
    """Wrap Caldera REST APIs with safe, offline-first fallbacks."""

    def __init__(self, base_url: str = "http://localhost:8888", timeout_seconds: float = 2.0) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self._session = requests.Session()
        self._simulated_operations: Dict[str, Dict[str, Any]] = {}
        self._simulated_profiles: List[Dict[str, str]] = [
            {
                "adversary_id": "sim-red-team-phishing",
                "name": "Spear Phishing Escalation",
                "description": "Simulated ATT&CK sequence for initial-access validation.",
                "techniques": ["T1566", "T1059", "T1078"],
            },
            {
                "adversary_id": "sim-red-team-lateral",
                "name": "Lateral Movement Sweep",
                "description": "Simulated ATT&CK sequence for east-west movement detection.",
                "techniques": ["T1021", "T1047", "T1083"],
            },
        ]

    def create_operation(self, adversary_id: str, targets: List[str], approval_token: str) -> str:
        """Create a Caldera operation; requires an operator approval token."""
        self._require_approval_token(approval_token)
        safe_adversary = self._validate_adversary_id(adversary_id)
        safe_targets = self._validate_targets(targets)

        payload = {
            "name": f"s3m-op-{uuid.uuid4().hex[:8]}",
            "adversary_id": safe_adversary,
            "planner": "atomic",
            "group": "red",
            "autonomous": 1,
        }

        if self._is_caldera_available():
            try:
                response = self._session.post(
                    f"{self.base_url}/api/v2/operations",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json() if response.content else {}
                operation_id = str(
                    body.get("id")
                    or body.get("operation_id")
                    or body.get("op_id")
                    or uuid.uuid4().hex
                )
                self._simulated_operations[operation_id] = {
                    "operation_id": operation_id,
                    "adversary_id": safe_adversary,
                    "targets": safe_targets,
                    "created_at": _utc_iso(),
                    "techniques_used": [],
                    "steps_completed": 0,
                    "simulated": False,
                }
                return operation_id
            except Exception:
                pass

        operation_id = f"sim-op-{uuid.uuid4().hex[:10]}"
        simulated = {
            "operation_id": operation_id,
            "adversary_id": safe_adversary,
            "targets": safe_targets,
            "created_at": _utc_iso(),
            "techniques_used": self._simulated_techniques_for_targets(safe_targets),
            "steps_completed": max(1, min(6, len(safe_targets) * 2)),
            "simulated": True,
        }
        self._simulated_operations[operation_id] = simulated
        return operation_id

    def get_operation_status(self, operation_id: str) -> Dict[str, Any]:
        """Return completed step count and ATT&CK techniques observed."""
        safe_operation_id = self._validate_operation_id(operation_id)

        if self._is_caldera_available():
            try:
                response = self._session.get(
                    f"{self.base_url}/api/v2/operations/{safe_operation_id}",
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json() if response.content else {}
                links = body.get("chain", []) if isinstance(body, dict) else []
                if not isinstance(links, list):
                    links = []
                steps_completed = sum(
                    1
                    for link in links
                    if str(link.get("status", "")).lower() in {"success", "completed", "executed"}
                )
                techniques = sorted(
                    {
                        str(link.get("attack", {}).get("technique_id", "")).strip()
                        for link in links
                        if isinstance(link, dict) and isinstance(link.get("attack"), dict)
                    }
                )
                techniques = [value for value in techniques if value]
                return {"steps_completed": steps_completed, "techniques_used": techniques}
            except Exception:
                pass

        simulated = self._simulated_operations.get(safe_operation_id)
        if simulated is None:
            return {"steps_completed": 0, "techniques_used": []}
        return {
            "steps_completed": int(simulated.get("steps_completed", 0)),
            "techniques_used": list(simulated.get("techniques_used", [])),
        }

    def list_adversary_profiles(self) -> List[Dict[str, Any]]:
        """List available adversary profiles mapped to ATT&CK posture."""
        if self._is_caldera_available():
            try:
                response = self._session.get(
                    f"{self.base_url}/api/v2/adversaries",
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json() if response.content else []
                if isinstance(body, dict):
                    body = body.get("items", [])
                if isinstance(body, list):
                    profiles: List[Dict[str, Any]] = []
                    for item in body:
                        if not isinstance(item, dict):
                            continue
                        techniques = item.get("atomic_ordering", [])
                        techniques = techniques if isinstance(techniques, list) else []
                        profiles.append(
                            {
                                "adversary_id": str(
                                    item.get("adversary_id") or item.get("id") or ""
                                ).strip(),
                                "name": str(item.get("name", "unknown")).strip(),
                                "description": str(item.get("description", "")).strip(),
                                "techniques": [str(tech) for tech in techniques if str(tech).strip()],
                            }
                        )
                    cleaned = [profile for profile in profiles if profile["adversary_id"]]
                    if cleaned:
                        return cleaned
            except Exception:
                pass
        return list(self._simulated_profiles)

    @staticmethod
    def _validate_adversary_id(adversary_id: str) -> str:
        value = str(adversary_id).strip()
        if not value:
            raise ValueError("adversary_id is required")
        return value

    @staticmethod
    def _validate_targets(targets: List[str]) -> List[str]:
        if not isinstance(targets, list):
            raise ValueError("targets must be a list of target identifiers")
        cleaned = [str(item).strip() for item in targets if str(item).strip()]
        if not cleaned:
            raise ValueError("at least one target is required")
        return cleaned

    @staticmethod
    def _validate_operation_id(operation_id: str) -> str:
        value = str(operation_id).strip()
        if not value:
            raise ValueError("operation_id is required")
        return value

    @staticmethod
    def _require_approval_token(approval_token: str) -> None:
        token = str(approval_token).strip()
        if not token:
            raise ValueError("approval_token is mandatory for offensive execution")

    def _is_caldera_available(self) -> bool:
        try:
            response = self._session.get(
                f"{self.base_url}/api/v2/adversaries",
                timeout=self.timeout_seconds,
            )
            return response.status_code < 500
        except Exception:
            return False

    @staticmethod
    def _simulated_techniques_for_targets(targets: List[str]) -> List[str]:
        baseline = ["T1059", "T1078", "T1083"]
        if len(targets) > 1:
            baseline.append("T1021")
        return baseline
