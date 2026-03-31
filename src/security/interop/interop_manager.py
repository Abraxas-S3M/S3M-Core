"""Multi-protocol security interoperability manager for S3M."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.security.interop.bml_adapter import BMLAdapter
from src.security.interop.c2sim_adapter import C2SIMAdapter
from src.security.interop.dis_adapter import DISAdapter


class InteropManager:
    """Coordinates DIS/C2SIM/BML protocol adapters for coalition exchange."""

    def __init__(self) -> None:
        self.dis_adapter = DISAdapter()
        self.c2sim_adapter = C2SIMAdapter()
        self.bml_adapter = BMLAdapter()

        self._status: Dict[str, Dict[str, Any]] = {
            "dis": {"enabled": False, "connected": False, "messages_sent": 0, "messages_received": 0},
            "c2sim": {"enabled": False, "connected": False, "messages_sent": 0, "messages_received": 0},
            "bml": {"enabled": False, "connected": True, "messages_sent": 0, "messages_received": 0},
        }
        self._history: List[Dict[str, Any]] = []

    def _record(self, protocol: str, direction: str, message_type: str, data: Any, raw: str = "") -> None:
        self._history.append(
            {
                "protocol": protocol,
                "direction": direction,
                "message_type": message_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw": raw,
            }
        )
        if len(self._history) > 5000:
            self._history = self._history[-5000:]

    def enable_protocol(self, protocol: str, config: dict | None = None) -> bool:
        protocol = protocol.lower().strip()
        config = config or {}
        if protocol == "dis":
            self.dis_adapter = DISAdapter(
                exercise_id=int(config.get("exercise_id", 1)),
                site_id=int(config.get("site_id", 1)),
                app_id=int(config.get("app_id", 1)),
                broadcast_address=str(config.get("broadcast_address", "255.255.255.255")),
                port=int(config.get("port", 3000)),
            )
            ok = self.dis_adapter.connect()
            self._status["dis"]["enabled"] = True
            self._status["dis"]["connected"] = ok
            return ok
        if protocol == "c2sim":
            self.c2sim_adapter = C2SIMAdapter(
                server_url=config.get("server_url"),
                namespace=str(config.get("namespace", "http://www.sisostds.org/schemas/C2SIM/1.1")),
            )
            ok = self.c2sim_adapter.connect(config.get("server_url"))
            self._status["c2sim"]["enabled"] = True
            self._status["c2sim"]["connected"] = ok
            return ok
        if protocol == "bml":
            self._status["bml"]["enabled"] = True
            self._status["bml"]["connected"] = True
            return True
        return False

    def disable_protocol(self, protocol: str) -> None:
        protocol = protocol.lower().strip()
        if protocol == "dis":
            self.dis_adapter.disconnect()
        elif protocol == "c2sim":
            self.c2sim_adapter.disconnect()
        elif protocol == "bml":
            pass
        if protocol in self._status:
            self._status[protocol]["enabled"] = False
            self._status[protocol]["connected"] = False

    def get_protocol_status(self) -> dict:
        return {
            "dis": dict(self._status["dis"]),
            "c2sim": dict(self._status["c2sim"]),
            "bml": dict(self._status["bml"]),
        }

    def send_entity_update(self, entity: Any) -> dict:
        result = {"dis": False, "c2sim": False}
        if self._status["dis"]["enabled"] and self._status["dis"]["connected"]:
            payload = entity if isinstance(entity, dict) else self.dis_adapter.sim_entity_to_dis(entity)
            ok = self.dis_adapter.send_entity_update(payload)
            result["dis"] = ok
            if ok:
                self._status["dis"]["messages_sent"] += 1
                self._record("dis", "outbound", "entity_state", payload)

        if self._status["c2sim"]["enabled"]:
            entity_dict = entity if isinstance(entity, dict) else self.dis_adapter.sim_entity_to_dis(entity)
            xml = self.c2sim_adapter.entity_to_position_report(entity_dict)
            ok = self.c2sim_adapter.send_message(xml)
            result["c2sim"] = ok
            if ok:
                self._status["c2sim"]["messages_sent"] += 1
                self._record("c2sim", "outbound", "position_report", entity_dict, raw=xml)
        return result

    def send_mission(self, mission: Any) -> dict:
        accepted = {"c2sim": False}
        if self._status["c2sim"]["enabled"]:
            xml = self.c2sim_adapter.mission_to_order(mission)
            ok = self.c2sim_adapter.send_message(xml)
            accepted["c2sim"] = ok
            if ok:
                self._status["c2sim"]["messages_sent"] += 1
                self._record("c2sim", "outbound", "order", {"mission": str(getattr(mission, "mission_id", "unknown"))}, raw=xml)
        return accepted

    def send_aar(self, aar: Any) -> dict:
        accepted = {"c2sim": False, "bml": False}
        if self._status["c2sim"]["enabled"]:
            xml = self.c2sim_adapter.aar_to_report(aar)
            ok = self.c2sim_adapter.send_message(xml)
            accepted["c2sim"] = ok
            if ok:
                self._status["c2sim"]["messages_sent"] += 1
                self._record("c2sim", "outbound", "report", {"aar": str(getattr(aar, "aar_id", "unknown"))}, raw=xml)
        if self._status["bml"]["enabled"]:
            xml = self.bml_adapter.generate_aar_report(aar)
            accepted["bml"] = True
            self._status["bml"]["messages_sent"] += 1
            self._record("bml", "outbound", "aar_report", {"aar": str(getattr(aar, "aar_id", "unknown"))}, raw=xml)
        return accepted

    def receive_all(self) -> List[dict]:
        messages: List[dict] = []

        if self._status["dis"]["enabled"] and self._status["dis"]["connected"]:
            dis_data = self.dis_adapter.receive()
            if dis_data:
                msg = {
                    "protocol": "dis",
                    "message_type": "entity_state",
                    "data": dis_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "raw": "",
                }
                messages.append(msg)
                self._status["dis"]["messages_received"] += 1
                self._record("dis", "inbound", "entity_state", dis_data)

        if self._status["c2sim"]["enabled"]:
            xml_msgs = self.c2sim_adapter.receive_messages()
            for raw in xml_msgs:
                parsed = {"raw_message": raw}
                if "<Order" in raw:
                    try:
                        parsed = self.c2sim_adapter.order_to_mission(raw)
                    except Exception:
                        parsed = {"raw_message": raw}
                msg = {
                    "protocol": "c2sim",
                    "message_type": "xml",
                    "data": parsed,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "raw": raw,
                }
                messages.append(msg)
                self._status["c2sim"]["messages_received"] += 1
                self._record("c2sim", "inbound", "xml", parsed, raw=raw)

        return messages

    def get_message_history(
        self, protocol: str | None = None, direction: str | None = None, limit: int = 50
    ) -> List[dict]:
        rows = self._history
        if protocol:
            rows = [r for r in rows if r["protocol"] == protocol.lower().strip()]
        if direction:
            rows = [r for r in rows if r["direction"] == direction.lower().strip()]
        return rows[-max(1, limit) :]

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protocols": self.get_protocol_status(),
            "history_entries": len(self._history),
        }
