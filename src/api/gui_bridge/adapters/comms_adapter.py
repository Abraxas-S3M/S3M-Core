"""Communications workspace adapter - thin wrapper over existing comms routes.

Internal dependencies:
- src.api.comms_routes (comms_router)
- services.comms.comms_manager.CommsManager
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.api.gui_bridge.models.gui_schemas import (
    GUICommsData,
    GUICommsMessage,
    GUIRelayStatus,
    MessagePriority,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommsAdapter:
    def __init__(self):
        self._comms = None
        self._store = None
        self._use_store_messages = False
        try:
            from services.comms.comms_manager import CommsManager

            self._comms = CommsManager()
        except Exception:
            pass
        try:
            from src.persistence.store_seeder import seed_store_if_empty

            self._store = seed_store_if_empty()
            self._use_store_messages = self._store.has_data("messages")
        except Exception:
            pass

    def get_messages(self) -> dict:
        try:
            from src.api.comms_routes import _comms_manager

            messages_raw = (
                _comms_manager.get_messages()
                if hasattr(_comms_manager, "get_messages")
                else []
            )
            inbox = []
            for m in messages_raw if isinstance(messages_raw, list) else []:
                md = (
                    m
                    if isinstance(m, dict)
                    else (m.model_dump() if hasattr(m, "model_dump") else {})
                )
                inbox.append(
                    {
                        "id": md.get("message_id", md.get("id", "")),
                        "from": md.get("sender", md.get("from", "UNKNOWN")),
                        "to": md.get("recipient", md.get("to", "OPS-CELL")),
                        "subject": md.get("subject", ""),
                        "body": md.get("body", md.get("content", "")),
                        "read": md.get("read", False),
                        "priority": md.get("priority", "routine"),
                        "timestamp": md.get("timestamp", _now_iso()),
                    }
                )
            if inbox:
                self._persist_rows("messages", inbox)
            result = {
                "inbox": inbox if inbox else self._get_stored_or_default_inbox(),
                "relayQueue": [],
                "updatedAt": _now_iso(),
            }
            emit_training_record("comms", {"query": "messages"}, result)
            return result
        except Exception:
            result = {
                "inbox": self._get_stored_or_default_inbox(),
                "relayQueue": [],
                "updatedAt": _now_iso(),
            }
            emit_training_record("comms", {"query": "messages"}, result)
            return result

    async def send_message(self, payload: Dict[str, Any]) -> dict:
        try:
            from src.api.comms_routes import _comms_manager

            result = _comms_manager.send(
                sender=payload.get("from", "OPS-CELL"),
                recipient=payload.get("to", ""),
                subject=payload.get("subject", ""),
                body=payload.get("body", ""),
                priority=payload.get("priority", "routine"),
            )
            from src.api.gui_bridge.timeline_service import timeline_service

            timeline_service.emit(
                title=f"Message sent to {payload.get('to', 'UNKNOWN')}",
                category="comms",
                severity="LOW",
                details=payload.get("subject", ""),
            )
            return {
                "status": "sent",
                "messageId": getattr(result, "message_id", "unknown"),
                "updatedAt": _now_iso(),
            }
        except Exception as e:
            return {"status": "error", "detail": str(e), "updatedAt": _now_iso()}

    def get_bearer_health(self) -> dict:
        bearers = self._default_bearers()
        mesh_status = self._default_mesh_status()
        try:
            from services.comms.bearer_bridge import BearerBridge
        except Exception:
            BearerBridge = None

        try:
            from services.comms.mesh_monitor import MeshNetworkMonitor
        except Exception:
            MeshNetworkMonitor = None

        try:
            if BearerBridge is not None:
                bridge = BearerBridge()
                status = bridge.get_status() if hasattr(bridge, "get_status") else []
                if isinstance(status, list):
                    bearers = status
        except Exception:
            pass

        try:
            if MeshNetworkMonitor is not None:
                monitor = MeshNetworkMonitor(node_manager=self._resolve_node_manager())
                status = monitor.get_mesh_status()
                if isinstance(status, dict):
                    mesh_status = status
        except Exception:
            pass

        return {"bearers": bearers, "mesh": mesh_status, "updatedAt": _now_iso()}

    def get_degradation_advice(self, bearer_status: dict = None) -> dict:
        """Route to Phi-3 Medium tactical engine for comms fallback recommendations."""
        mesh_context = self._default_degradation_context()
        try:
            from services.comms.mesh_monitor import MeshNetworkMonitor

            monitor = MeshNetworkMonitor(node_manager=self._resolve_node_manager())
            context = monitor.estimate_degradation()
            if isinstance(context, dict):
                mesh_context = context
        except Exception:
            pass

        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest
            from src.llm_core.engine_registry import TaskDomain

            orch = Orchestrator()
            prompt = (
                f"Given bearer status: {bearer_status or {}}. "
                f"Mesh degradation context: {mesh_context}. "
                "Recommend comms fallback procedures for this tactical network."
            )
            result = orch.query(
                QueryRequest(
                    prompt=prompt,
                    domain=TaskDomain.TACTICAL,
                    max_tokens=256,
                )
            )
            return {
                "advice": result.get("text", ""),
                "engine": "phi3-medium",
                "updatedAt": _now_iso(),
            }
        except Exception:
            return {
                "advice": "Switch to HF as primary. Queue non-critical traffic.",
                "updatedAt": _now_iso(),
            }

    @staticmethod
    def _default_inbox():
        return [
            {
                "id": "MSG-1",
                "from": "JTF-HQ",
                "to": "OPS-CELL",
                "subject": "ROE reminder",
                "body": "Maintain positive identification before engagement in populated areas.",
                "read": False,
                "priority": "priority",
                "timestamp": _now_iso(),
            },
            {
                "id": "MSG-2",
                "from": "ISR-DESK",
                "to": "OPS-CELL",
                "subject": "UAV-02 feed update",
                "body": "Thermal feed quality restored, correlation confidence increased.",
                "read": True,
                "priority": "routine",
                "timestamp": _now_iso(),
            },
        ]

    def _persist_rows(self, table: str, rows: list[dict]) -> None:
        if self._store is None:
            return
        for row in rows:
            if isinstance(row, dict):
                self._store.upsert(table, row)
        if table == "messages":
            self._use_store_messages = True

    def _get_stored_or_default_inbox(self) -> list[dict]:
        if self._store is not None and self._use_store_messages:
            stored = self._store.get_all("messages")
            if stored:
                return stored
        defaults = self._default_inbox()
        self._persist_rows("messages", defaults)
        return defaults
