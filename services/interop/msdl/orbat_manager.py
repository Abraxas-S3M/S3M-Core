"""ORBAT manager for coalition force structures and MSDL interoperability."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional
from uuid import uuid4

from services.interop.models import ForceStructure, ORBATUnit, build_orbat_unit
from services.interop.msdl.generator import MSDLGenerator
from services.interop.msdl.parser import MSDLParser


class ORBATManager:
    """Maintains force structures and converts between ORBAT and MSDL."""

    def __init__(self):
        self.forces: Dict[str, ForceStructure] = {}
        self.generator = MSDLGenerator()
        self.parser = MSDLParser()

    def create_force(self, name, affiliation, country_code=178) -> ForceStructure:
        force = ForceStructure(
            force_id=f"force-{uuid4().hex[:10]}",
            force_name=str(name),
            affiliation=str(affiliation),
            units=[],
            country_code=int(country_code),
        )
        self.forces[force.force_id] = force
        return force

    def add_unit(self, force_id, unit: ORBATUnit):
        force = self.forces.get(force_id)
        if force is None:
            raise ValueError(f"Force not found: {force_id}")
        force.units.append(unit)
        if unit.parent_unit_id:
            parent = force.get_unit(unit.parent_unit_id)
            if parent is not None and unit.unit_id not in parent.subordinate_ids:
                parent.subordinate_ids.append(unit.unit_id)

    def create_unit(
        self,
        name,
        designation,
        echelon,
        unit_type,
        affiliation,
        country_code=178,
        parent_unit_id=None,
    ) -> ORBATUnit:
        symbol = f"{affiliation[:1].upper()}-{unit_type[:3].upper()}-{echelon[:3].upper()}"
        return build_orbat_unit(
            name=str(name),
            designation=str(designation),
            echelon=str(echelon),
            unit_type=str(unit_type),
            affiliation=str(affiliation),
            country_code=int(country_code),
            parent_unit_id=parent_unit_id,
            nato_symbol=symbol,
        )

    def get_force(self, force_id) -> Optional[ForceStructure]:
        return self.forces.get(force_id)

    def get_unit(self, unit_id) -> Optional[ORBATUnit]:
        for force in self.forces.values():
            unit = force.get_unit(unit_id)
            if unit is not None:
                return unit
        return None

    def get_all_forces(self) -> List[ForceStructure]:
        return list(self.forces.values())

    def build_hierarchy(self, force_id) -> dict:
        force = self.forces.get(force_id)
        if force is None:
            raise ValueError(f"Force not found: {force_id}")
        units = {u.unit_id: u for u in force.units}
        children: Dict[str, List[ORBATUnit]] = {}
        roots: List[ORBATUnit] = []
        for unit in force.units:
            if unit.parent_unit_id and unit.parent_unit_id in units:
                children.setdefault(unit.parent_unit_id, []).append(unit)
            else:
                roots.append(unit)

        def build(unit: ORBATUnit) -> dict:
            return {
                "unit": unit,
                "subordinates": [build(child) for child in children.get(unit.unit_id, [])],
            }

        return {"force": force, "hierarchy": [build(root) for root in roots]}

    def to_msdl(self) -> str:
        scenario = {
            "scenario_id": f"orbat-{uuid4().hex[:8]}",
            "name": "ORBAT Export",
            "description": "Force structure export from ORBAT manager",
            "forces": [force.to_dict() for force in self.forces.values()],
            "environment": {"terrain": "desert", "weather": "clear", "time_of_day": "0600"},
            "overlay": {},
            "version": "1.0",
        }
        return self.generator.generate_from_s3m_scenario(scenario)

    def from_msdl(self, xml_str: str):
        scenario = self.parser.parse(xml_str)
        self.forces = {force.force_id: force for force in scenario.forces}

    def export_to_scenario(self) -> dict:
        return {
            "scenario_id": f"scenario-{uuid4().hex[:8]}",
            "name": "ORBAT Scenario",
            "description": "Scenario generated from ORBAT force structures",
            "forces": [force.to_dict() for force in self.forces.values()],
            "environment": {"terrain": "desert", "weather": "clear", "time_of_day": "0600"},
            "objectives": [],
            "rules_of_engagement": "SELF_DEFENSE_ONLY",
            "duration_seconds": 7200,
            "parameters": {"source": "orbat_manager"},
        }

    def create_saudi_template(self) -> ForceStructure:
        force = self.create_force("Royal Saudi Land Forces Template", "friendly", country_code=178)

        hq = build_orbat_unit(
            name="Saudi Joint Corps HQ",
            designation="Headquarters",
            echelon="corps",
            unit_type="headquarters",
            affiliation="friendly",
            country_code=178,
            nato_symbol="SFGPUCHQ---*****",
            strength=600,
            commander="LTG Command",
        )
        self.add_unit(force.force_id, hq)

        armored = build_orbat_unit(
            name="1st Armored Brigade",
            designation="1st Armored Brigade",
            echelon="brigade",
            unit_type="armor",
            affiliation="friendly",
            country_code=178,
            parent_unit_id=hq.unit_id,
            nato_symbol="SFGPUCA----*****",
            strength=3200,
        )
        self.add_unit(force.force_id, armored)
        for idx in range(1, 4):
            battalion = build_orbat_unit(
                name=f"1st Armored Battalion {idx}",
                designation=f"{idx}th Armored Battalion",
                echelon="battalion",
                unit_type="armor",
                affiliation="friendly",
                country_code=178,
                parent_unit_id=armored.unit_id,
                nato_symbol="SFGPUCAA---*****",
                strength=700,
            )
            self.add_unit(force.force_id, battalion)

        mech = build_orbat_unit(
            name="2nd Mechanized Brigade",
            designation="2nd Mechanized Brigade",
            echelon="brigade",
            unit_type="infantry",
            affiliation="friendly",
            country_code=178,
            parent_unit_id=hq.unit_id,
            nato_symbol="SFGPUCI----*****",
            strength=3000,
        )
        self.add_unit(force.force_id, mech)
        for idx in range(1, 4):
            battalion = build_orbat_unit(
                name=f"2nd Mechanized Battalion {idx}",
                designation=f"{idx}th Mechanized Battalion",
                echelon="battalion",
                unit_type="infantry",
                affiliation="friendly",
                country_code=178,
                parent_unit_id=mech.unit_id,
                nato_symbol="SFGPUCIA---*****",
                strength=650,
            )
            self.add_unit(force.force_id, battalion)

        aviation = build_orbat_unit(
            name="Aviation Wing",
            designation="Army Aviation Wing",
            echelon="brigade",
            unit_type="aviation",
            affiliation="friendly",
            country_code=178,
            parent_unit_id=hq.unit_id,
            nato_symbol="SFGPUCV----*****",
            strength=900,
        )
        self.add_unit(force.force_id, aviation)
        for idx in range(1, 3):
            squadron = build_orbat_unit(
                name=f"Aviation Squadron {idx}",
                designation=f"{idx}th Aviation Squadron",
                echelon="company",
                unit_type="aviation",
                affiliation="friendly",
                country_code=178,
                parent_unit_id=aviation.unit_id,
                nato_symbol="SFGPUCVA---*****",
                strength=220,
            )
            self.add_unit(force.force_id, squadron)

        air_def = build_orbat_unit(
            name="Air Defense Group",
            designation="Air Defense Group",
            echelon="battalion",
            unit_type="air_defense",
            affiliation="friendly",
            country_code=178,
            parent_unit_id=hq.unit_id,
            nato_symbol="SFGPUCD----*****",
            strength=700,
        )
        self.add_unit(force.force_id, air_def)

        logistics = build_orbat_unit(
            name="Logistics Battalion",
            designation="Logistics Battalion",
            echelon="battalion",
            unit_type="logistics",
            affiliation="friendly",
            country_code=178,
            parent_unit_id=hq.unit_id,
            nato_symbol="SFGPUCL----*****",
            strength=850,
        )
        self.add_unit(force.force_id, logistics)

        return force

    def get_statistics(self) -> dict:
        total_forces = len(self.forces)
        all_units = [unit for force in self.forces.values() for unit in force.units]
        by_echelon = Counter(unit.echelon for unit in all_units)
        by_type = Counter(unit.unit_type for unit in all_units)
        return {
            "total_forces": total_forces,
            "total_units": len(all_units),
            "total_strength": sum(unit.strength for unit in all_units),
            "by_echelon": dict(by_echelon),
            "by_type": dict(by_type),
        }
