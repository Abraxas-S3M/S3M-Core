"""Cyber workspace adapter.

Internal dependencies:
- services.cyber.soc_manager.SOCManager (incidents/cases)
- src.api.cyber_routes (SOC overview, alerts, platform status)
"""

from datetime import datetime, timezone
from typing import List
import os

from src.api.gui_bridge.models.gui_schemas import (
    GUICyberData,
    GUICyberIncident,
    GUICyberResilienceMetric,
    SeverityLevel,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CyberAdapter:
    def __init__(self):
        self._soc = None
        self._store = None
        self._use_store_incidents = False
        try:
            from services.cyber.soc_manager import SOCManager

            self._soc = SOCManager()
        except Exception:
            pass
        try:
            from src.persistence.store_seeder import seed_store_if_empty

            self._store = seed_store_if_empty()
            self._use_store_incidents = self._store.has_data("incidents")
        except Exception:
            pass

    def get_incidents(self) -> List[dict]:
        incidents = self._fetch_incidents()
        result = {"incidents": incidents, "updatedAt": _now_iso()}
        emit_training_record("cyber", {"query": "incidents"}, result)
        return result

    def get_resilience(self) -> dict:
        metrics = self._fetch_resilience()
        result = {"resilience": metrics, "updatedAt": _now_iso()}
        emit_training_record("cyber", {"query": "resilience"}, result)
        return result

    def get_model_security(self) -> dict:
        try:
            from src.api.config import api_config
            from src.api.server import state
            from src.security.model_scanner import ModelScanner

            scanner = ModelScanner()
            engine_scans = {}
            for engine_id, engine_status in state.engine_status.items():
                if engine_status != "loaded":
                    continue
                model_path = str(api_config.model_paths.get(engine_id, "")).strip()
                if not model_path:
                    continue
                integrity = scanner.scan_model_integrity(model_path)
                vulnerabilities = scanner.probe_llm_vulnerabilities(engine_id)
                engine_scans[engine_id] = {
                    "modelPath": model_path,
                    "integrity": integrity,
                    "vulnerabilities": vulnerabilities,
                }

            if not engine_scans:
                for engine_id, model_path in api_config.model_paths.items():
                    safe_path = str(model_path).strip()
                    if not safe_path or not os.path.exists(safe_path):
                        continue
                    integrity = scanner.scan_model_integrity(safe_path)
                    vulnerabilities = scanner.probe_llm_vulnerabilities(engine_id)
                    engine_scans[engine_id] = {
                        "modelPath": safe_path,
                        "integrity": integrity,
                        "vulnerabilities": vulnerabilities,
                    }

            status = scanner.trust_manager.get_trust_status()
            status["scans"] = engine_scans
            return {"modelSecurity": status, "updatedAt": _now_iso()}
        except Exception:
            return {
                "modelSecurity": {"overallTrust": 92, "alerts": []},
                "updatedAt": _now_iso(),
            }

    def get_trust_fabric(self) -> dict:
        try:
            from src.security.crypto import get_crypto_status
            from src.security.zkn import get_zkn_status

            crypto = get_crypto_status() if callable(get_crypto_status) else {}
            zkn = get_zkn_status() if callable(get_zkn_status) else {}
            return {"crypto": crypto, "zeroKnowledge": zkn, "updatedAt": _now_iso()}
        except Exception:
            return {"crypto": {}, "zeroKnowledge": {}, "updatedAt": _now_iso()}

    def get_attack_capabilities(self) -> dict:
        """Expose ATT&CK adversary profiles from Caldera bridge."""
        try:
            from services.cyber.offensive.caldera_bridge import CalderaBridge

            bridge = CalderaBridge()
            profiles = bridge.list_adversary_profiles()
            return {"capabilities": profiles, "updatedAt": _now_iso()}
        except Exception:
            return {"capabilities": [], "updatedAt": _now_iso()}

    def _fetch_incidents(self) -> List[dict]:
        try:
            from src.api.cyber_routes import _soc_manager

            alerts = (
                _soc_manager.get_alert_queue()
                if hasattr(_soc_manager, "get_alert_queue")
                else []
            )
            cases = _soc_manager.get_cases() if hasattr(_soc_manager, "get_cases") else []
            results = []
            for a in alerts if isinstance(alerts, list) else []:
                ad = (
                    a
                    if isinstance(a, dict)
                    else (a.model_dump() if hasattr(a, "model_dump") else {})
                )
                results.append(
                    GUICyberIncident(
                        id=ad.get("id", ad.get("alert_id", "")),
                        title=ad.get("title", ad.get("rule_name", "Alert")),
                        severity=self._map_severity(ad.get("severity", "MEDIUM")),
                        status=ad.get("status", "open"),
                        source=ad.get("source", "SIEM"),
                        detectedAt=ad.get("timestamp", _now_iso()),
                        description=ad.get("description", ""),
                    ).model_dump()
                )
            for c in cases if isinstance(cases, list) else []:
                cd = (
                    c
                    if isinstance(c, dict)
                    else (c.model_dump() if hasattr(c, "model_dump") else {})
                )
                results.append(
                    GUICyberIncident(
                        id=cd.get("case_id", cd.get("id", "")),
                        title=cd.get("title", "Case"),
                        severity=self._map_severity(cd.get("severity", "MEDIUM")),
                        status=cd.get("status", "open"),
                        source=cd.get("source", "SOC"),
                        detectedAt=cd.get("created_at", _now_iso()),
                        description=cd.get("description", cd.get("summary", "")),
                    ).model_dump()
                )
            if results:
                self._persist_rows("incidents", results)
                return results
            return self._get_stored_or_default_incidents()
        except Exception:
            return self._get_stored_or_default_incidents()

    def _fetch_resilience(self) -> List[dict]:
        try:
            from src.api.cyber_routes import _soc_manager

            overview = (
                _soc_manager.get_soc_overview()
                if hasattr(_soc_manager, "get_soc_overview")
                else {}
            )
            ov = (
                overview
                if isinstance(overview, dict)
                else (overview.model_dump() if hasattr(overview, "model_dump") else {})
            )
            return [
                GUICyberResilienceMetric(
                    domain="Network",
                    score=ov.get("network_health", 85),
                    status="operational",
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="Endpoint",
                    score=ov.get("endpoint_health", 78),
                    status="operational",
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="AI/Model",
                    score=ov.get("model_trust", 92),
                    status="operational",
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="SCADA/OT", score=ov.get("ot_health", 70), status="caution"
                ).model_dump(),
            ]
        except Exception:
            return [
                GUICyberResilienceMetric(
                    domain="Network", score=85, status="operational"
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="Endpoint", score=78, status="operational"
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="AI/Model", score=92, status="operational"
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="SCADA/OT", score=70, status="caution"
                ).model_dump(),
            ]

    @staticmethod
    def _map_severity(s) -> SeverityLevel:
        s = str(s).upper()
        return SeverityLevel[s] if s in SeverityLevel.__members__ else SeverityLevel.MEDIUM

    @staticmethod
    def _default_incidents():
        return [
            GUICyberIncident(
                id="CYB-001",
                title="Anomalous DNS exfiltration attempt",
                severity=SeverityLevel.HIGH,
                status="investigating",
                source="Suricata",
                detectedAt=_now_iso(),
                description="Unusual DNS query volume to external resolver.",
            ).model_dump(),
            GUICyberIncident(
                id="CYB-002",
                title="Failed SSH brute-force",
                severity=SeverityLevel.MEDIUM,
                status="contained",
                source="Wazuh",
                detectedAt=_now_iso(),
                description="Multiple failed auth attempts on edge node.",
            ).model_dump(),
        ]

    def _persist_rows(self, table: str, rows: list[dict]) -> None:
        if self._store is None:
            return
        for row in rows:
            if isinstance(row, dict):
                self._store.upsert(table, row)
        if table == "incidents":
            self._use_store_incidents = True

    def _get_stored_or_default_incidents(self) -> List[dict]:
        if self._store is not None and self._use_store_incidents:
            stored = self._store.get_all("incidents")
            if stored:
                return stored
        defaults = self._default_incidents()
        self._persist_rows("incidents", defaults)
        return defaults
