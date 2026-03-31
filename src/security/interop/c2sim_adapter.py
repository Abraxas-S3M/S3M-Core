"""C2SIM adapter for coalition order/report interoperability."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET


@dataclass
class _MessageLogEntry:
    direction: str
    timestamp: str
    message_type: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "timestamp": self.timestamp,
            "type": self.message_type,
            "content": self.content,
        }


class C2SIMAdapter:
    """SISO C2SIM XML exchange adapter with online/offline modes."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        namespace: str = "http://www.sisostds.org/schemas/C2SIM/1.1",
    ) -> None:
        self.server_url = server_url
        self.namespace = namespace
        self.connected = False
        self.offline_mode = True
        self._message_log: List[_MessageLogEntry] = []
        self._outbox_dir = Path("data/interop/c2sim_outbox")
        self._inbox_dir = Path("data/interop/c2sim_inbox")
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        self._inbox_dir.mkdir(parents=True, exist_ok=True)

    def connect(self, server_url: Optional[str] = None) -> bool:
        if server_url:
            self.server_url = server_url
        if not self.server_url:
            self.connected = False
            self.offline_mode = True
            return False

        status_url = f"{self.server_url.rstrip('/')}/C2SIMServer/status"
        try:
            with urllib.request.urlopen(status_url, timeout=2) as response:
                if 200 <= response.status < 300:
                    self.connected = True
                    self.offline_mode = False
                    return True
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass

        self.connected = False
        self.offline_mode = True
        return False

    def disconnect(self) -> None:
        self.connected = False
        self.offline_mode = True

    def mission_to_order(self, mission: Any) -> str:
        mission_id = self._mission_attr(mission, "mission_id", f"mission-{uuid.uuid4().hex[:8]}")
        mission_type = self._mission_type_value(self._mission_attr(mission, "mission_type", "PATROL"))
        agent_ids = self._mission_attr(mission, "agent_ids", [])
        roe = self._mission_attr(mission, "rules_of_engagement", "SELF_DEFENSE_ONLY")
        waypoints = self._mission_attr(mission, "waypoints", [])
        if not isinstance(waypoints, list):
            waypoints = []

        order = ET.Element("Order", {"xmlns": self.namespace})
        ET.SubElement(order, "OrderID").text = str(mission_id)
        ET.SubElement(order, "OrderType").text = str(mission_type)
        ET.SubElement(order, "IssuedTime").text = datetime.now(timezone.utc).isoformat()
        tasking_order = ET.SubElement(order, "TaskingOrder")
        task = ET.SubElement(tasking_order, "Task")
        ET.SubElement(task, "TaskID").text = str(uuid.uuid4())
        ET.SubElement(task, "TaskType").text = str(mission_type)
        ET.SubElement(task, "AssignedTo").text = ",".join(str(a) for a in agent_ids)

        location = ET.SubElement(task, "Location")
        for wp in waypoints:
            coord = ET.SubElement(location, "Coordinate")
            x, y, z = self._extract_xyz(wp)
            ET.SubElement(coord, "X").text = str(x)
            ET.SubElement(coord, "Y").text = str(y)
            ET.SubElement(coord, "Z").text = str(z)

        ET.SubElement(task, "RulesOfEngagement").text = str(roe)
        xml_payload = ET.tostring(order, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_payload}'

    def order_to_mission(self, xml_str: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_str)
        task = self._find_any(root, "Task")
        if task is None:
            raise ValueError("C2SIM Order missing Task")

        mission_type = self._text(self._find_any(root, "OrderType")) or self._text(self._find_any(task, "TaskType")) or "PATROL"
        assigned = self._text(self._find_any(task, "AssignedTo")) or ""
        roe = self._text(self._find_any(task, "RulesOfEngagement")) or "SELF_DEFENSE_ONLY"

        waypoints: List[Dict[str, float]] = []
        for coord in task.findall(".//{*}Coordinate"):
            x = self._safe_float(self._text(self._find_any(coord, "X")), 0.0)
            y = self._safe_float(self._text(self._find_any(coord, "Y")), 0.0)
            z = self._safe_float(self._text(self._find_any(coord, "Z")), 0.0)
            waypoints.append({"x": x, "y": y, "z": z})

        return {
            "mission_type": mission_type,
            "waypoints": waypoints,
            "roe": roe,
            "assigned_agents": [v for v in (a.strip() for a in assigned.split(",")) if v],
        }

    def aar_to_report(self, aar: Any) -> str:
        report = ET.Element("Report", {"xmlns": self.namespace})
        ET.SubElement(report, "ReportID").text = str(uuid.uuid4())
        ET.SubElement(report, "ReportType").text = "AAR"
        ET.SubElement(report, "ReportTime").text = datetime.now(timezone.utc).isoformat()

        content = ET.SubElement(report, "Content")
        ET.SubElement(content, "Outcome").text = str(self._mission_attr(aar, "outcome", "unknown"))
        ET.SubElement(content, "FriendlyLosses").text = str(self._mission_attr(aar, "friendly_losses", 0))
        ET.SubElement(content, "EnemyLosses").text = str(self._mission_attr(aar, "enemy_losses", 0))

        objectives = ET.SubElement(content, "Objectives")
        for obj in self._mission_attr(aar, "objectives_met", []):
            ET.SubElement(objectives, "Met").text = str(obj)
        for obj in self._mission_attr(aar, "objectives_failed", []):
            ET.SubElement(objectives, "Failed").text = str(obj)

        timeline_node = ET.SubElement(content, "TimelineSummary")
        timeline_data = self._mission_attr(aar, "timeline", [])
        if isinstance(timeline_data, list):
            for event in timeline_data[:50]:
                entry = ET.SubElement(timeline_node, "Event")
                ET.SubElement(entry, "Summary").text = json.dumps(event, ensure_ascii=False)

        xml_payload = ET.tostring(report, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_payload}'

    def scenario_from_init(self, xml_str: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_str)
        scenario_id = self._text(self._find_any(root, "ScenarioID")) or f"c2sim-{uuid.uuid4().hex[:8]}"
        name = self._text(self._find_any(root, "Name")) or "C2SIM Imported Scenario"

        terrain: Dict[str, Any] = {}
        terrain_node = self._find_any(root, "Terrain")
        if terrain_node is not None:
            for child in list(terrain_node):
                terrain[self._tag(child)] = self._text(child)

        weather: Dict[str, Any] = {}
        weather_node = self._find_any(root, "Weather")
        if weather_node is not None:
            for child in list(weather_node):
                weather[self._tag(child)] = self._text(child)

        return {
            "scenario_id": scenario_id,
            "name": name,
            "description": "Imported from C2SIM initialization message",
            "scenario_type": self._text(self._find_any(root, "ScenarioType")) or "imported",
            "terrain": terrain,
            "weather": weather,
            "objectives": [],
            "rules_of_engagement": self._text(self._find_any(root, "RulesOfEngagement")) or "SELF_DEFENSE_ONLY",
            "duration_seconds": int(self._safe_float(self._text(self._find_any(root, "DurationSeconds")), 3600)),
            "parameters": {"source": "C2SIM"},
        }

    def entity_to_position_report(self, entity: Dict[str, Any]) -> str:
        """Convert an entity state into a C2SIM-style position report XML."""
        report = ET.Element("Report", {"xmlns": self.namespace})
        ET.SubElement(report, "ReportType").text = "POSITION"
        ET.SubElement(report, "ReportTime").text = datetime.now(timezone.utc).isoformat()
        ent = ET.SubElement(report, "Entity")
        ET.SubElement(ent, "EntityID").text = str(entity.get("entity_id", "unknown"))
        ET.SubElement(ent, "Allegiance").text = str(entity.get("allegiance", "neutral"))
        ET.SubElement(ent, "EntityType").text = str(entity.get("entity_type", "UNKNOWN"))
        location = entity.get("location", {})
        coord = ET.SubElement(ent, "Coordinate")
        ET.SubElement(coord, "X").text = str(location.get("x", 0.0))
        ET.SubElement(coord, "Y").text = str(location.get("y", 0.0))
        ET.SubElement(coord, "Z").text = str(location.get("z", 0.0))
        xml_payload = ET.tostring(report, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_payload}'

    def send_message(self, xml_str: str) -> bool:
        timestamp = datetime.now(timezone.utc).isoformat()
        msg_type = self._extract_root_tag(xml_str)
        if self.connected and not self.offline_mode and self.server_url:
            try:
                endpoint = f"{self.server_url.rstrip('/')}/C2SIMServer/message"
                req = urllib.request.Request(
                    endpoint,
                    data=xml_str.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    ok = 200 <= response.status < 300
                self._message_log.append(_MessageLogEntry("outbound", timestamp, msg_type, xml_str))
                return ok
            except (urllib.error.URLError, TimeoutError, ValueError):
                # tactical fallback: persist locally when remote link unavailable
                self.connected = False
                self.offline_mode = True

        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.xml"
        path = self._outbox_dir / filename
        path.write_text(xml_str, encoding="utf-8")
        self._message_log.append(_MessageLogEntry("outbound", timestamp, msg_type, xml_str))
        return True

    def receive_messages(self) -> List[str]:
        messages: List[str] = []
        timestamp = datetime.now(timezone.utc).isoformat()
        if self.connected and not self.offline_mode and self.server_url:
            try:
                endpoint = f"{self.server_url.rstrip('/')}/C2SIMServer/messages"
                with urllib.request.urlopen(endpoint, timeout=3) as response:
                    payload = response.read().decode("utf-8")
                if payload.strip().startswith("["):
                    remote_messages = json.loads(payload)
                    if isinstance(remote_messages, list):
                        messages.extend(str(msg) for msg in remote_messages)
                elif payload.strip():
                    messages.append(payload)
            except Exception:
                self.connected = False
                self.offline_mode = True

        if self.offline_mode:
            for path in sorted(self._inbox_dir.glob("*.xml")):
                messages.append(path.read_text(encoding="utf-8"))

        for msg in messages:
            self._message_log.append(
                _MessageLogEntry("inbound", timestamp, self._extract_root_tag(msg), msg)
            )
        return messages

    def get_message_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return [entry.to_dict() for entry in self._message_log[-limit:]]

    @staticmethod
    def _mission_attr(obj: Any, name: str, default: Any) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def _mission_type_value(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _extract_xyz(waypoint: Any) -> tuple[float, float, float]:
        if isinstance(waypoint, dict):
            return (
                float(waypoint.get("x", waypoint.get("X", 0.0))),
                float(waypoint.get("y", waypoint.get("Y", 0.0))),
                float(waypoint.get("z", waypoint.get("Z", 0.0))),
            )
        if hasattr(waypoint, "x") and hasattr(waypoint, "y") and hasattr(waypoint, "z"):
            return (float(waypoint.x), float(waypoint.y), float(waypoint.z))
        if isinstance(waypoint, (list, tuple)) and len(waypoint) >= 3:
            return (float(waypoint[0]), float(waypoint[1]), float(waypoint[2]))
        return (0.0, 0.0, 0.0)

    @staticmethod
    def _tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    @classmethod
    def _find_any(cls, root: ET.Element, local_name: str) -> Optional[ET.Element]:
        for element in root.iter():
            if cls._tag(element) == local_name:
                return element
        return None

    @staticmethod
    def _text(node: Optional[ET.Element]) -> Optional[str]:
        if node is None or node.text is None:
            return None
        return node.text.strip()

    @staticmethod
    def _safe_float(value: Optional[str], default: float) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_root_tag(xml_str: str) -> str:
        try:
            root = ET.fromstring(xml_str)
            return root.tag.rsplit("}", 1)[-1]
        except ET.ParseError:
            return "Unknown"
