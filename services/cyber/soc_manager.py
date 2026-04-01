"""Central orchestrator for S3M Layer 07 Cyber Defense Operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.cyber.ir_platforms import IRPlatformBridge
from services.cyber.log_aggregation import LogAggregator
from services.cyber.models import CaseVerdict, IncidentCase
from services.cyber.soc_dashboard import SOCDashboardProvider
from services.cyber.soar import SOAREngine
from services.cyber.triage import AlertTriage, CaseManager


class SOCManager:
    """End-to-end SOC pipeline from threat events through response workflows."""

    def __init__(self) -> None:
        self.alert_triage = AlertTriage()
        self.case_manager = CaseManager()
        self.ir_bridge = IRPlatformBridge()
        self.soar_engine = SOAREngine()
        self.log_aggregator = LogAggregator()
        self.soc_dashboard = SOCDashboardProvider()
        self.soc_dashboard.bind(self.case_manager, self.alert_triage, self.soar_engine, self.ir_bridge)
        # Lazy to avoid circular import during module load.
        from services.cyber.training import CyberTrainingManager

        self.cyber_training = CyberTrainingManager(soc_manager=self, auto_create_manager=False)
        self._processed_events = 0

    def process_event(self, event: Any) -> dict:
        triage_result = self.alert_triage.triage(event)
        case: Optional[IncidentCase] = None
        enrichments: List[dict] = []
        soar_result: Optional[dict] = None

        if triage_result["auto_create_case"]:
            case = self.case_manager.create_from_triage(triage_result, event)
            self.soar_engine.register_case(case)

            enrich_objects = self.ir_bridge.enrich_observables_from_dicts(case.observables)
            enrichments = [item.to_dict() for item in enrich_objects]
            for enrichment in enrich_objects:
                self.case_manager.add_enrichment(case.case_id, enrichment)

            if triage_result.get("mitre") is not None:
                mapping = triage_result["mitre"]
                if mapping.tactic_id not in case.mitre_tactics:
                    case.mitre_tactics.append(mapping.tactic_id)
                if mapping.technique_id not in case.mitre_techniques:
                    case.mitre_techniques.append(mapping.technique_id)

            soar_result = self.soar_engine.auto_respond(case)

        logs = self.log_aggregator.ingest_threat_event(event)
        self._processed_events += 1

        result = {
            "event_id": triage_result["event_id"],
            "triage": {
                "severity": triage_result["severity"].value,
                "triage_score": triage_result["triage_score"],
                "observable_count": len(triage_result["observables"]),
                "auto_create_case": triage_result["auto_create_case"],
                "mitre": triage_result["mitre"].to_dict() if triage_result["mitre"] else None,
            },
            "case_id": case.case_id if case else None,
            "enrichments": enrichments,
            "soar": soar_result,
            "logs": logs,
        }
        return result

    def process_batch(self, events: List[Any]) -> dict:
        results = [self.process_event(event) for event in events]
        created = [item for item in results if item.get("case_id")]
        return {
            "processed": len(results),
            "cases_created": len(created),
            "results": results,
        }

    def get_case(self, case_id):
        return self.case_manager.get_case(case_id)

    def get_cases(self, **kwargs):
        return self.case_manager.get_cases(**kwargs)

    def get_open_cases(self):
        return self.case_manager.get_open_cases()

    def assign_case(self, case_id, analyst):
        return self.case_manager.assign_analyst(case_id, analyst)

    def escalate_case(self, case_id, reason):
        return self.case_manager.escalate(case_id, reason)

    def resolve_case(self, case_id, verdict, notes):
        return self.case_manager.resolve(case_id, CaseVerdict.from_value(verdict), notes)

    def search_logs(self, query):
        return self.log_aggregator.search(query)

    def generate_soc_report(self) -> str:
        stats = self.case_manager.get_stats()
        overview = self.soc_dashboard.get_soc_overview()
        open_cases = self.get_open_cases()
        # Tactical shift report template serves as Mistral fallback in offline deployments.
        lines = [
            "S3M SOC Shift Report",
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
            f"Processed Events: {self._processed_events}",
            f"Total Cases: {stats['total']}",
            f"Open Cases: {overview['open_cases']}",
            f"Mean Resolution Hours: {overview['mean_resolution_hours']}",
            "Case Status Breakdown:",
        ]
        for key, value in overview["cases_by_status"].items():
            lines.append(f"  - {key}: {value}")
        lines.append("Open Case Snapshot:")
        if not open_cases:
            lines.append("  - No open cases")
        for case in open_cases[:5]:
            lines.append(f"  - {case.case_id} [{case.severity.value}] {case.title}")
        lines.append("Commander Guidance: Maintain containment posture and prioritize CRITICAL/HIGH cases.")
        return "\n".join(lines)

    def get_soc_status(self) -> dict:
        return {
            "triage": self.alert_triage.get_triage_stats(),
            "cases": self.case_manager.get_stats(),
            "platforms": self.ir_bridge.get_platform_status(),
            "soar": self.soar_engine.health_check(),
            "logs": self.log_aggregator.get_backend_status(),
            "dashboard": {"status": "ready"},
            "training": {"exercises": len(self.cyber_training.get_exercise_history())},
        }

    def health_check(self) -> dict:
        status = self.get_soc_status()
        return {
            "status": "operational",
            "processed_events": self._processed_events,
            "subsystems": status,
        }
