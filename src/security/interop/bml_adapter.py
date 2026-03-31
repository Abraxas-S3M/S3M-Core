"""Battle Management Language (BML) adapter for tactical interoperability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


class BMLAdapter:
    """Parses BML orders and generates BML reports for coalition workflows."""

    TASK_MAP = {
        "MOVE": "MOVE_TO",
        "ADVANCE": "MOVE_TO",
        "DEFEND": "HOLD",
        "HOLD": "HOLD",
        "ATTACK": "ENGAGE",
        "ENGAGE": "ENGAGE",
        "WITHDRAW": "RTB",
        "RETREAT": "RTB",
        "PATROL": "MOVE_TO",
        "RECON": "MOVE_TO",
    }

    def __init__(self) -> None:
        self.message_log: List[Dict[str, Any]] = []

    def parse_order(self, xml_str: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_str)
        who = self._read_text(root, ["Who", "WHO", "Unit", "Agent"], default="ALL")
        what_raw = self._read_text(root, ["What", "WHAT", "TaskType", "Action"], default="MOVE")
        where_node = self._find_node(root, ["Where", "WHERE", "Location"])
        when = self._read_text(root, ["When", "WHEN", "Time", "TimeConstraint"], default="")
        why = self._read_text(root, ["Why", "WHY", "Objective"], default="")

        waypoint = self._parse_coordinate(where_node)
        what = self.TASK_MAP.get(what_raw.strip().upper(), "MOVE_TO")
        if what_raw.strip().upper() in {"PATROL", "RECON"}:
            patrol = True
        else:
            patrol = False

        parsed = {
            "who": who,
            "what": what,
            "where": waypoint,
            "when": when,
            "why": why,
            "patrol": patrol,
            "raw_xml": xml_str,
        }
        self._log("inbound", "BML_ORDER", parsed)
        return parsed

    def order_to_swarm_command(self, parsed_order: Dict[str, Any]) -> Dict[str, Any]:
        # Tactical mapping keeps vocabulary aligned with existing swarm command schema.
        target_agents = [a.strip() for a in str(parsed_order.get("who", "ALL")).split(",") if a.strip()]
        if not target_agents:
            target_agents = ["ALL"]
        return {
            "target_agents": target_agents,
            "command_type": parsed_order.get("what", "MOVE_TO"),
            "parameters": {
                "waypoint": parsed_order.get("where", (0.0, 0.0, 0.0)),
                "objective": parsed_order.get("why", ""),
                "time_constraint": parsed_order.get("when", ""),
                "patrol": bool(parsed_order.get("patrol", False)),
            },
        }

    def generate_report(self, events: list, report_type: str = "SITREP") -> str:
        report_type_upper = (report_type or "SITREP").upper()
        if report_type_upper not in {"SITREP", "SPOTREP", "INTREP"}:
            report_type_upper = "SITREP"

        root = ET.Element("BMLReport")
        ET.SubElement(root, "ReportType").text = report_type_upper
        ET.SubElement(root, "ReportTime").text = datetime.now(timezone.utc).isoformat()
        ET.SubElement(root, "ReportingUnit").text = "S3M"
        content = ET.SubElement(root, "Content")

        for event in events:
            obs = ET.SubElement(content, "Observation")
            ET.SubElement(obs, "Who").text = self._event_field(event, "source", "unknown")
            ET.SubElement(obs, "What").text = self._event_field(event, "event_type", "observation")
            where = ET.SubElement(obs, "Where")
            coord = ET.SubElement(where, "Coordinate")
            loc = self._event_location(event)
            ET.SubElement(coord, "X").text = str(loc[0])
            ET.SubElement(coord, "Y").text = str(loc[1])
            ET.SubElement(coord, "Z").text = str(loc[2])
            ET.SubElement(obs, "When").text = self._event_field(
                event, "event_time", datetime.now(timezone.utc).isoformat()
            )

        xml_str = ET.tostring(root, encoding="unicode")
        self._log("outbound", "BML_REPORT", {"report_type": report_type_upper, "count": len(events)})
        return xml_str

    def generate_aar_report(self, aar: Any) -> str:
        payload = self._to_dict(aar)
        root = ET.Element("BMLAfterActionReport")
        ET.SubElement(root, "ReportTime").text = datetime.now(timezone.utc).isoformat()
        ET.SubElement(root, "ReportingUnit").text = "S3M"
        ET.SubElement(root, "Outcome").text = str(payload.get("outcome", "unknown"))
        ET.SubElement(root, "FriendlyLosses").text = str(payload.get("friendly_losses", 0))
        ET.SubElement(root, "EnemyLosses").text = str(payload.get("enemy_losses", 0))
        objectives = ET.SubElement(root, "Objectives")
        for obj in payload.get("objectives_met", []):
            ET.SubElement(objectives, "Met").text = str(obj)
        for obj in payload.get("objectives_failed", []):
            ET.SubElement(objectives, "Failed").text = str(obj)
        xml_str = ET.tostring(root, encoding="unicode")
        self._log("outbound", "BML_AAR", {"outcome": payload.get("outcome", "unknown")})
        return xml_str

    def validate_bml(self, xml_str: str) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            return False, [f"Invalid XML: {exc}"]

        report_type = self._read_text(root, ["ReportType"], default=None)
        has_content = root.find("Content") is not None or root.find(".//Task") is not None
        if not report_type and root.tag not in {"Order", "BMLOrder", "BMLReport", "BMLAfterActionReport"}:
            errors.append("Missing ReportType or unsupported root element")
        if not has_content and root.tag not in {"Order", "BMLOrder", "BMLAfterActionReport"}:
            errors.append("Missing Content section")

        for coord in root.findall(".//Coordinate"):
            x = self._read_text(coord, ["X"], default=None)
            y = self._read_text(coord, ["Y"], default=None)
            z = self._read_text(coord, ["Z"], default="0")
            try:
                float(x)  # type: ignore[arg-type]
                float(y)  # type: ignore[arg-type]
                float(z)
            except (TypeError, ValueError):
                errors.append("Coordinate fields must be numeric")
                break
        return len(errors) == 0, errors

    def _log(self, direction: str, message_type: str, details: Dict[str, Any]) -> None:
        self.message_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "direction": direction,
                "type": message_type,
                "details": details,
            }
        )
        if len(self.message_log) > 1000:
            del self.message_log[:-1000]

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        if hasattr(value, "to_dict") and callable(value.to_dict):
            return dict(value.to_dict())
        if isinstance(value, dict):
            return dict(value)
        return dict(getattr(value, "__dict__", {}))

    @staticmethod
    def _read_text(root: ET.Element, keys: List[str], default: Optional[str] = "") -> Optional[str]:
        for key in keys:
            node = root.find(f".//{key}")
            if node is not None and node.text is not None:
                return node.text
        return default

    @staticmethod
    def _find_node(root: ET.Element, keys: List[str]) -> Optional[ET.Element]:
        for key in keys:
            node = root.find(f".//{key}")
            if node is not None:
                return node
        return None

    @staticmethod
    def _parse_coordinate(node: Optional[ET.Element]) -> Tuple[float, float, float]:
        if node is None:
            return (0.0, 0.0, 0.0)
        coord_node = node.find(".//Coordinate")
        c = coord_node if coord_node is not None else node
        try:
            x = float((c.findtext("X") or "0").strip())
            y = float((c.findtext("Y") or "0").strip())
            z = float((c.findtext("Z") or "0").strip())
            return (x, y, z)
        except (TypeError, ValueError):
            return (0.0, 0.0, 0.0)

    @staticmethod
    def _event_field(event: Any, key: str, default: Any = "") -> str:
        if isinstance(event, dict):
            return str(event.get(key, default))
        return str(getattr(event, key, default))

    @staticmethod
    def _event_location(event: Any) -> Tuple[float, float, float]:
        loc = None
        if isinstance(event, dict):
            loc = event.get("location")
        else:
            loc = getattr(event, "location", None)
        if isinstance(loc, dict):
            return (float(loc.get("x", 0.0)), float(loc.get("y", 0.0)), float(loc.get("z", 0.0)))
        if isinstance(loc, (list, tuple)) and len(loc) >= 3:
            return (float(loc[0]), float(loc[1]), float(loc[2]))
        return (0.0, 0.0, 0.0)
