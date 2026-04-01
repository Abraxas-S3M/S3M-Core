"""C2SIM XML message generation and parsing utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4
from xml.etree import ElementTree as ET


class C2SIMMessageFactory:
    """Builds and parses core C2SIM message types with stdlib XML."""

    def __init__(self, namespace: str = "http://www.sisostds.org/schemas/C2SIM/1.1"):
        self.namespace = namespace

    def _root(self, tag: str) -> ET.Element:
        return ET.Element(tag, {"xmlns": self.namespace})

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    @classmethod
    def _find(cls, root: ET.Element, local_name: str):
        for node in root.iter():
            if cls._tag(node) == local_name:
                return node
        return None

    @classmethod
    def _text(cls, root: ET.Element, local_name: str, default: str = "") -> str:
        node = cls._find(root, local_name)
        if node is None or node.text is None:
            return default
        return node.text.strip()

    def create_order(
        self,
        order_id,
        issuer,
        task_type,
        assigned_units: List[str],
        waypoints: List[tuple],
        roe: str,
        start_time: str = None,
    ) -> str:
        root = self._root("Order")
        ET.SubElement(root, "OrderID").text = str(order_id)
        ET.SubElement(root, "Issuer").text = str(issuer)
        ET.SubElement(root, "IssuedTime").text = self._iso_now()
        tasking = ET.SubElement(root, "TaskingOrder")
        task = ET.SubElement(tasking, "Task")
        ET.SubElement(task, "TaskID").text = str(uuid4())
        ET.SubElement(task, "TaskType").text = str(task_type)
        ET.SubElement(task, "AssignedUnits").text = ",".join(str(unit) for unit in assigned_units)
        where = ET.SubElement(task, "WhereClause")
        for idx, waypoint in enumerate(waypoints):
            point = ET.SubElement(where, "Waypoint")
            ET.SubElement(point, "Sequence").text = str(idx)
            ET.SubElement(point, "Latitude").text = str(waypoint[0])
            ET.SubElement(point, "Longitude").text = str(waypoint[1])
            ET.SubElement(point, "Altitude").text = str(waypoint[2] if len(waypoint) > 2 else 0.0)
        when = ET.SubElement(task, "WhenClause")
        ET.SubElement(when, "StartTime").text = start_time or self._iso_now()
        ET.SubElement(task, "RulesOfEngagement").text = str(roe)
        return ET.tostring(root, encoding="unicode")

    def create_report(self, report_id, reporter, report_type: str, content: dict) -> str:
        root = self._root("Report")
        ET.SubElement(root, "ReportID").text = str(report_id)
        ET.SubElement(root, "Reporter").text = str(reporter)
        ET.SubElement(root, "ReportType").text = str(report_type)
        ET.SubElement(root, "ReportTime").text = self._iso_now()
        content_node = ET.SubElement(root, "Content")
        for key, value in dict(content or {}).items():
            ET.SubElement(content_node, str(key)).text = str(value)
        return ET.tostring(root, encoding="unicode")

    def create_initialization(self, scenario: dict) -> str:
        root = self._root("Initialization")
        ET.SubElement(root, "ScenarioID").text = str(scenario.get("scenario_id", f"scenario-{uuid4().hex[:8]}"))
        ET.SubElement(root, "Name").text = str(scenario.get("name", "C2SIM Scenario"))
        forces_node = ET.SubElement(root, "Forces")
        for force in scenario.get("forces", []):
            force_node = ET.SubElement(forces_node, "Force")
            ET.SubElement(force_node, "ForceID").text = str(force.get("force_id", "force"))
            ET.SubElement(force_node, "ForceName").text = str(force.get("force_name", "Unknown"))
            units_node = ET.SubElement(force_node, "Units")
            for unit in force.get("units", []):
                unit_node = ET.SubElement(units_node, "Unit")
                ET.SubElement(unit_node, "UnitID").text = str(unit.get("unit_id", "unit"))
                ET.SubElement(unit_node, "Name").text = str(unit.get("name", "Unit"))
                pos = unit.get("position")
                if pos:
                    pnode = ET.SubElement(unit_node, "InitialPosition")
                    ET.SubElement(pnode, "Latitude").text = str(pos[0])
                    ET.SubElement(pnode, "Longitude").text = str(pos[1])
        env = ET.SubElement(root, "Environment")
        for key, value in dict(scenario.get("environment", {})).items():
            ET.SubElement(env, str(key)).text = str(value)
        return ET.tostring(root, encoding="unicode")

    def create_plan(self, plan_id, name, phases: List[dict]) -> str:
        root = self._root("Plan")
        ET.SubElement(root, "PlanID").text = str(plan_id)
        ET.SubElement(root, "Name").text = str(name)
        seq = ET.SubElement(root, "PhaseSequence")
        for index, phase in enumerate(phases):
            p = ET.SubElement(seq, "Phase")
            ET.SubElement(p, "Index").text = str(index)
            ET.SubElement(p, "PhaseName").text = str(phase.get("name", f"Phase {index + 1}"))
            ET.SubElement(p, "Objective").text = str(phase.get("objective", ""))
        return ET.tostring(root, encoding="unicode")

    def parse_order(self, xml_str: str) -> dict:
        root = ET.fromstring(xml_str)
        task = self._find(root, "Task")
        units = self._text(task if task is not None else root, "AssignedUnits", "")
        waypoints = []
        if task is not None:
            for waypoint in task.findall(".//{*}Waypoint"):
                lat = float(self._text(waypoint, "Latitude", "0"))
                lon = float(self._text(waypoint, "Longitude", "0"))
                alt = float(self._text(waypoint, "Altitude", "0"))
                waypoints.append((lat, lon, alt))
        return {
            "order_id": self._text(root, "OrderID", ""),
            "issuer": self._text(root, "Issuer", ""),
            "task_type": self._text(root, "TaskType", ""),
            "assigned_units": [x for x in (u.strip() for u in units.split(",")) if x],
            "waypoints": waypoints,
            "roe": self._text(root, "RulesOfEngagement", ""),
            "start_time": self._text(root, "StartTime", ""),
        }

    def parse_report(self, xml_str: str) -> dict:
        root = ET.fromstring(xml_str)
        content_node = self._find(root, "Content")
        content: Dict[str, str] = {}
        if content_node is not None:
            for child in list(content_node):
                content[self._tag(child)] = (child.text or "").strip()
        return {
            "report_id": self._text(root, "ReportID", ""),
            "reporter": self._text(root, "Reporter", ""),
            "report_type": self._text(root, "ReportType", ""),
            "content": content,
        }

    def parse_initialization(self, xml_str: str) -> dict:
        root = ET.fromstring(xml_str)
        forces = []
        for force in root.findall(".//{*}Force"):
            units = []
            for unit in force.findall(".//{*}Unit"):
                pos = self._find(unit, "InitialPosition")
                position = None
                if pos is not None:
                    position = (
                        float(self._text(pos, "Latitude", "0")),
                        float(self._text(pos, "Longitude", "0")),
                    )
                units.append(
                    {
                        "unit_id": self._text(unit, "UnitID", ""),
                        "name": self._text(unit, "Name", ""),
                        "position": position,
                    }
                )
            forces.append(
                {
                    "force_id": self._text(force, "ForceID", ""),
                    "force_name": self._text(force, "ForceName", ""),
                    "units": units,
                }
            )
        env = self._find(root, "Environment")
        environment = {}
        if env is not None:
            for child in list(env):
                environment[self._tag(child)] = (child.text or "").strip()
        return {
            "scenario_id": self._text(root, "ScenarioID", ""),
            "name": self._text(root, "Name", ""),
            "forces": forces,
            "environment": environment,
        }

    def parse_any(self, xml_str: str) -> dict:
        root = ET.fromstring(xml_str)
        tag = self._tag(root)
        if tag == "Order":
            return {"message_type": "Order", "data": self.parse_order(xml_str)}
        if tag == "Report":
            return {"message_type": "Report", "data": self.parse_report(xml_str)}
        if tag == "Initialization":
            return {"message_type": "Initialization", "data": self.parse_initialization(xml_str)}
        if tag == "Plan":
            return {"message_type": "Plan", "data": {"xml": xml_str}}
        return {"message_type": "Unknown", "data": {"xml": xml_str}}

    def validate(self, xml_str: str) -> tuple[bool, List[str]]:
        errors: List[str] = []
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            return (False, [f"Malformed XML: {exc}"])
        tag = self._tag(root)
        if tag == "Order":
            required = ["OrderID", "TaskingOrder", "TaskType"]
        elif tag == "Report":
            required = ["ReportID", "ReportType", "Content"]
        elif tag == "Initialization":
            required = ["ScenarioID", "Forces", "Environment"]
        elif tag == "Plan":
            required = ["PlanID", "PhaseSequence"]
        else:
            required = []
            errors.append(f"Unsupported root element: {tag}")
        for element in required:
            if self._find(root, element) is None:
                errors.append(f"Missing required element: {element}")
        return (len(errors) == 0, errors)
