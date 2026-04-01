"""Shuffle SOAR adapter with offline outbox fallback."""

from __future__ import annotations

import json
import os
from typing import List

from services.cyber.ir_platforms.base import IRPlatformAdapter
from services.cyber.models import IncidentCase, Playbook


class ShuffleAdapter(IRPlatformAdapter):
    """Integrates S3M playbooks with Shuffle when available."""

    def __init__(self, url: str = "http://localhost:3001", api_key: str = None) -> None:
        super().__init__(url=url, api_key=api_key, outbox_dir="data/cyber/shuffle_outbox")

    def connect(self) -> bool:
        return self._safe_request("GET", "/api/v1/workflows") is not None

    def trigger_workflow(self, workflow_id: str, case: IncidentCase) -> dict:
        payload = {
            "workflow_id": workflow_id,
            "execution_argument": case.to_dict(),
        }
        response = self._safe_request("POST", f"/api/v1/workflows/{workflow_id}/execute", payload)
        if response is None:
            self._write_outbox("trigger_workflow", payload)
            return {"status": "queued_offline", "error": "Shuffle unavailable"}
        return {"status": "triggered", "execution_id": response.get("execution_id", "")}

    def list_workflows(self) -> List[dict]:
        response = self._safe_request("GET", "/api/v1/workflows")
        if response is None:
            return []
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, list):
                return data
        return []

    def get_execution_status(self, execution_id: str) -> dict:
        response = self._safe_request("GET", f"/api/v1/executions/{execution_id}")
        if response is None:
            return {"execution_id": execution_id, "status": "pending_offline"}
        return response if isinstance(response, dict) else {"raw": str(response)}

    def import_playbook(self, playbook: Playbook) -> dict:
        workflow = {
            "name": playbook.name,
            "description": playbook.description,
            "tags": playbook.tags,
            "actions": [step.to_dict() for step in playbook.steps],
        }
        response = self._safe_request("POST", "/api/v1/workflows", workflow)
        if response is None:
            self._write_outbox("import_playbook", workflow)
            return {"status": "queued_offline", "error": "Shuffle unavailable"}
        return {"status": "imported", "workflow_id": response.get("id", playbook.playbook_id)}

