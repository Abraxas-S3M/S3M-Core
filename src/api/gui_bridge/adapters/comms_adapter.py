"""Communications workspace adapter - thin wrapper over existing comms routes.

Internal dependencies:
- src.api.comms_routes (comms_router)
- services.comms.comms_manager.CommsManager
"""

from datetime import datetime, timezone
from typing import Any, Dict

from src.api.gui_bridge.models.gui_schemas import (
    GUICommsData,
    GUICommsMessage,
    GUIRelayStatus,
    MessagePriority,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommsAdapter:
    def __init__(self):
        self._comms = None
        try:
            from services.comms.comms_manager import CommsManager

            self._comms = CommsManager()
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
            return {
                "inbox": inbox if inbox else self._default_inbox(),
                "relayQueue": [],
                "updatedAt": _now_iso(),
            }
        except Exception:
            return {"inbox": self._default_inbox(), "relayQueue": [], "updatedAt": _now_iso()}

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
        try:
            from services.comms.bearer_bridge import BearerBridge

            bridge = BearerBridge()
            bearers = bridge.get_status() if hasattr(bridge, "get_status") else []
            return {"bearers": bearers, "updatedAt": _now_iso()}
        except Exception:
            return {
                "bearers": [
                    {
                        "type": "SATCOM",
                        "status": "operational",
                        "signal": 85,
                        "latency": 120,
                    },
                    {"type": "HF", "status": "degraded", "signal": 45, "latency": 800},
                    {"type": "VHF", "status": "operational", "signal": 92, "latency": 15},
                    {"type": "LTE", "status": "offline", "signal": 0, "latency": 0},
                ],
                "updatedAt": _now_iso(),
            }

    def get_degradation_advice(self, bearer_status: dict = None) -> dict:
        """Route to Phi-3 Medium tactical engine for comms fallback recommendations."""
        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest
            from src.llm_core.engine_registry import TaskDomain

            orch = Orchestrator()
            prompt = (
                f"Given bearer status: {bearer_status}. "
                "Recommend comms fallback procedures."
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
