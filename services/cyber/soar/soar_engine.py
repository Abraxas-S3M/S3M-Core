"""SOAR orchestration engine for automated SOC playbook response."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from services.cyber.models import IncidentCase
from services.cyber.soar.playbook_executor import PlaybookExecutor
from services.cyber.soar.playbook_library import PlaybookLibrary
from services.cyber.soar.shuffle_adapter import ShuffleAdapter


class SOAREngine:
    """Coordinates playbook matching and execution with Shuffle fallback."""

    def __init__(self) -> None:
        self.playbook_library = PlaybookLibrary()
        self.playbook_library.load_all()
        self.playbook_executor = PlaybookExecutor()
        self.shuffle_adapter = ShuffleAdapter()
        self._case_index: Dict[str, IncidentCase] = {}

    def register_case(self, case: IncidentCase) -> None:
        self._case_index[case.case_id] = case
        if len(self._case_index) > 10000:
            # Keep bounded memory for long-running SOC shifts.
            first_key = next(iter(self._case_index))
            del self._case_index[first_key]

    def auto_respond(self, case: IncidentCase) -> dict:
        self.register_case(case)
        playbook = self.playbook_library.match_playbook(case)
        if playbook is not None:
            return {
                "mode": "playbook",
                "matched_playbook_id": playbook.playbook_id,
                "result": self.playbook_executor.execute(playbook, case),
            }

        workflows = self.shuffle_adapter.list_workflows()
        if workflows:
            workflow_id = str(workflows[0].get("id", "default"))
            triggered = self.shuffle_adapter.trigger_workflow(workflow_id, case)
            return {"mode": "shuffle", "workflow_id": workflow_id, "result": triggered}

        recommendation = (
            "Manual review required: no direct playbook matched. "
            "Recommend analyst triage with IOC enrichment and containment readiness."
        )
        case.llm_recommendation = recommendation
        case.add_timeline_entry("manual_review", "soar_engine", recommendation)
        return {
            "mode": "manual_review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recommendation": recommendation,
        }

    def manual_execute(self, case_id: str, playbook_id: str) -> dict:
        case = self._case_index.get(case_id)
        if case is None:
            raise ValueError(f"Case not found for SOAR execution: {case_id}")
        playbook = self.playbook_library.get_playbook(playbook_id)
        if playbook is None:
            raise ValueError(f"Playbook not found: {playbook_id}")
        return self.playbook_executor.execute(playbook, case)

    def get_playbooks(self) -> list[dict]:
        return self.playbook_library.list_playbooks()

    def get_history(self) -> list[dict]:
        return self.playbook_executor.get_execution_history()

    def health_check(self) -> dict:
        return {
            "playbook_library_loaded": len(self.playbook_library.list_playbooks()) > 0,
            "shuffle_connected": self.shuffle_adapter.connect(),
            "executions_tracked": len(self.playbook_executor.get_execution_history(limit=1000)),
        }
