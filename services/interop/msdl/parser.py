"""MSDL parser for scenario and ORBAT interoperability exchange."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from services.interop.models import ForceStructure, MSDLScenario, ORBATUnit


class MSDLParser:
    """Parses MSDL XML into internal dataclasses."""

    UNIT_TYPE_MAP = {
        "armor": "armor",
        "armored": "armor",
        "mechanized": "armor",
        "infantry": "infantry",
        "artillery": "artillery",
        "airdefense": "air_defense",
        "air_defense": "air_defense",
        "aviation": "aviation",
        "engineer": "engineer",
        "logistics": "logistics",
        "hq": "headquarters",
        "headquarters": "headquarters",
        "specialforces": "special_forces",
        "special_forces": "special_forces",
        "naval": "naval",
        "cyber": "cyber",
    }

    def __init__(self):
        pass

    @staticmethod
    def _tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    @classmethod
    def _find(cls, root: ET.Element, local_name: str) -> Optional[ET.Element]:
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

    def parse(self, xml_str: str) -> MSDLScenario:
        root = ET.fromstring(xml_str)
        scenario_id = self._text(root, "ScenarioID", "msdl-scenario")
        name = self._text(root, "Name", "MSDL Scenario")
        description = self._text(root, "Description", "Imported from MSDL")
        version = self._text(root, "Version", "1.0")

        forces_node = self._find(root, "ForceSides")
        forces = self.parse_forces(forces_node) if forces_node is not None else []

        environment_node = self._find(root, "Environment")
        environment: Dict[str, str] = {}
        if environment_node is not None:
            for child in list(environment_node):
                environment[self._tag(child)] = (child.text or "").strip()

        overlay_node = self._find(root, "Overlay")
        overlay: Dict[str, object] = {}
        if overlay_node is not None:
            for child in list(overlay_node):
                key = self._tag(child)
                if list(child):
                    overlay[key] = [((item.text or "").strip()) for item in list(child)]
                else:
                    overlay[key] = (child.text or "").strip()

        return MSDLScenario(
            scenario_id=scenario_id,
            name=name,
            description=description,
            forces=forces,
            environment=environment,
            overlay=overlay,
            version=version,
            created_at=datetime.now(timezone.utc),
        )

    def parse_file(self, filepath: str) -> MSDLScenario:
        text = Path(filepath).read_text(encoding="utf-8")
        return self.parse(text)

    def parse_forces(self, xml_element) -> List[ForceStructure]:
        forces: List[ForceStructure] = []
        if xml_element is None:
            return forces
        for force_node in xml_element.findall(".//{*}ForceSide"):
            force_id = self._text(force_node, "ForceID", "force")
            force_name = self._text(force_node, "ForceName", force_id)
            affiliation = self._text(force_node, "Affiliation", "friendly")
            country_code = int(self._text(force_node, "CountryCode", "178") or "178")
            units: List[ORBATUnit] = []
            units_node = self._find(force_node, "Units")
            if units_node is not None:
                for unit_node in units_node.findall(".//{*}Unit"):
                    # Parse only roots here (no ParentUnitID) and recurse for children.
                    parent_id = self._text(unit_node, "ParentUnitID", "")
                    if parent_id:
                        continue
                    unit = self.parse_unit(unit_node, parent_id=None)
                    units.append(unit)
                    # Extract recursively linked subordinate units by id references.
                    for child_node in units_node.findall(".//{*}Unit"):
                        c_parent = self._text(child_node, "ParentUnitID", "")
                        if c_parent == unit.unit_id:
                            child = self.parse_unit(child_node, parent_id=unit.unit_id)
                            units.append(child)
                            unit.subordinate_ids.append(child.unit_id)
            forces.append(
                ForceStructure(
                    force_id=force_id,
                    force_name=force_name,
                    affiliation=affiliation,
                    units=units,
                    country_code=country_code,
                )
            )
        return forces

    def parse_unit(self, xml_element, parent_id=None) -> ORBATUnit:
        unit_id = self._text(xml_element, "UnitID", "unit")
        unit_type_raw = self._text(xml_element, "UnitType", "infantry").replace(" ", "_").lower()
        mapped_type = self.UNIT_TYPE_MAP.get(unit_type_raw, unit_type_raw)
        pos_node = self._find(xml_element, "Position")
        if pos_node is None:
            pos_node = self._find(xml_element, "InitialPosition")
        position = None
        if pos_node is not None:
            try:
                lat = float(self._text(pos_node, "Latitude", "0"))
                lon = float(self._text(pos_node, "Longitude", "0"))
                position = (lat, lon)
            except ValueError:
                position = None
        return ORBATUnit(
            unit_id=unit_id,
            name=self._text(xml_element, "Name", unit_id),
            designation=self._text(xml_element, "Designation", unit_id),
            echelon=self._text(xml_element, "Echelon", "company"),
            unit_type=mapped_type,
            affiliation=self._text(xml_element, "Affiliation", "friendly"),
            parent_unit_id=parent_id or self._text(xml_element, "ParentUnitID", "") or None,
            subordinate_ids=[
                (child.text or "").strip() for child in xml_element.findall(".//{*}SubordinateUnitIDs/{*}UnitID")
            ],
            country_code=int(self._text(xml_element, "CountryCode", "178") or "178"),
            nato_symbol=self._text(xml_element, "NATOSymbol", ""),
            strength=int(self._text(xml_element, "Strength", "0") or "0"),
            equipment=[],
            position=position,
            commander=self._text(xml_element, "Commander", "") or None,
        )

    def validate(self, xml_str: str) -> tuple[bool, List[str]]:
        errors: List[str] = []
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            return (False, [f"Malformed XML: {exc}"])
        if self._tag(root) != "MilitaryScenario":
            errors.append("Root element must be MilitaryScenario")
        for required in ("ScenarioID", "ForceSides"):
            if self._find(root, required) is None:
                errors.append(f"Missing required element: {required}")
        return (len(errors) == 0, errors)

