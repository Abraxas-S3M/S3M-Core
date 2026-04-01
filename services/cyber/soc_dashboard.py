"""SOC dashboard provider that aggregates Layer 07 cyber operations views."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from services.cyber.models import IncidentCase


class SOCDashboardProvider:
    """Produces SOC dashboard widgets from triage/case/playbook activity."""

    def __init__(self, case_manager=None, triage=None, soar=None, ir_bridge=None) -> None:
        self._case_manager = None
        self._triage = None
        self._soar = None
        self._ir_bridge = None
        if any(item is not None for item in [case_manager, triage, soar, ir_bridge]):
            self.bind(case_manager, triage, soar, ir_bridge)

    def bind(self, case_manager, triage, soar, ir_bridge) -> None:
        self._case_manager = case_manager
        self._triage = triage
        self._soar = soar
        self._ir_bridge = ir_bridge

    def _cases(self) -> List[IncidentCase]:
        if self._case_manager is None:
            return []
        return self._case_manager.get_cases(limit=10000)

    def get_soc_overview(self) -> dict:
        cases = self._cases()
        by_severity = Counter(case.severity.value for case in cases)
        by_status = Counter(case.status.value for case in cases)
        resolution_hours = [
            (case.duration_seconds() or 0.0) / 3600.0
            for case in cases
            if case.duration_seconds() is not None
        ]
        mean_resolution = (sum(resolution_hours) / len(resolution_hours)) if resolution_hours else 0.0
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        alerts_last_hour = 0
        if self._triage is not None:
            for alert in self._triage.get_alert_queue(limit=1000):
                try:
                    created = datetime.fromisoformat(str(alert.get("created_at")))
                except Exception:
                    continue
                if created >= one_hour_ago:
                    alerts_last_hour += 1
        platforms_online = []
        if self._ir_bridge is not None:
            platforms_online = [
                name for name, connected in self._ir_bridge.get_platform_status().items() if connected
            ]
        playbooks_today = 0
        if self._soar is not None:
            today = datetime.now(timezone.utc).date()
            for entry in self._soar.get_history():
                try:
                    ts_raw = entry.get("timestamp")
                    if ts_raw is None:
                        continue
                    ts = datetime.fromisoformat(str(ts_raw))
                except Exception:
                    continue
                if ts.date() == today:
                    playbooks_today += 1
        observables_counter = Counter()
        analyst_workload = Counter()
        for case in cases:
            if case.assigned_analyst:
                analyst_workload[case.assigned_analyst] += 1
            for obs in case.observables:
                value = str(obs.get("value", ""))
                if value:
                    observables_counter[value] += 1
        top_observables = [
            {"value": value, "count": count}
            for value, count in observables_counter.most_common(10)
        ]
        return {
            "open_cases": len([case for case in cases if case.is_open()]),
            "cases_by_severity": dict(by_severity),
            "cases_by_status": dict(by_status),
            "mean_resolution_hours": round(mean_resolution, 3),
            "alerts_last_hour": alerts_last_hour,
            "playbooks_executed_today": playbooks_today,
            "platforms_online": platforms_online,
            "mitre_heatmap": self.get_mitre_heatmap(),
            "top_observables": top_observables,
            "analyst_workload": dict(analyst_workload),
        }

    def get_alert_queue(self, severity: str = None, limit: int = 50) -> List[dict]:
        if self._triage is None:
            return []
        return self._triage.get_alert_queue(severity=severity, limit=limit)

    def get_mitre_heatmap(self) -> List[dict]:
        cases = self._cases()
        rows: Dict[tuple[str, str], dict] = {}
        for case in cases:
            for tactic_id in case.mitre_tactics or ["UNKNOWN"]:
                for technique_id in case.mitre_techniques or ["UNKNOWN"]:
                    key = (tactic_id, technique_id)
                    row = rows.setdefault(
                        key,
                        {
                            "tactic_id": tactic_id,
                            "tactic_name": tactic_id,
                            "technique_id": technique_id,
                            "technique_name": technique_id,
                            "count": 0,
                            "severity_sum": 0.0,
                        },
                    )
                    row["count"] += 1
                    row["severity_sum"] += {
                        "INFORMATIONAL": 1.0,
                        "LOW": 2.0,
                        "MEDIUM": 3.0,
                        "HIGH": 4.0,
                        "CRITICAL": 5.0,
                    }.get(case.severity.value, 1.0)
        output = []
        for row in rows.values():
            output.append(
                {
                    "tactic_id": row["tactic_id"],
                    "tactic_name": row["tactic_name"],
                    "technique_id": row["technique_id"],
                    "technique_name": row["technique_name"],
                    "count": row["count"],
                    "severity_avg": round(row["severity_sum"] / max(1, row["count"]), 3),
                }
            )
        output.sort(key=lambda item: item["count"], reverse=True)
        return output

    def get_analyst_workbench(self, analyst: str) -> dict:
        cases = [case for case in self._cases() if case.assigned_analyst == analyst]
        pending_enrichment = []
        playbook_results = []
        for case in cases:
            if not case.enrichments:
                pending_enrichment.append(case.case_id)
            playbook_results.extend(case.playbook_results)
        return {
            "analyst": analyst,
            "assigned_cases": [case.to_dict() for case in cases],
            "pending_enrichments": pending_enrichment,
            "playbook_results": playbook_results,
        }

    def get_ioc_feed(self, limit: int = 100) -> List[dict]:
        feed = []
        for case in self._cases():
            for observable in case.observables:
                row = dict(observable)
                row["case_id"] = case.case_id
                row["case_severity"] = case.severity.value
                row["case_status"] = case.status.value
                feed.append(row)
        feed.sort(key=lambda row: str(row.get("last_seen", "")), reverse=True)
        safe_limit = max(1, min(int(limit), 1000))
        return feed[:safe_limit]
