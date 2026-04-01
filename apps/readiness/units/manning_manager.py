"""Unit manning table manager for S3M readiness layer."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from apps.readiness.models import (
    Branch,
    ClearanceLevel,
    ManningSlot,
    Rank,
    UnitManning,
)


class UnitManningManager:
    """Create and maintain TO&E style slot-based manning tables."""

    def __init__(self, personnel_registry=None):
        self.personnel_registry = personnel_registry
        self.units: Dict[str, UnitManning] = {}
        self.slot_to_unit: Dict[str, str] = {}

    def create_unit(
        self,
        unit_name_en: str,
        unit_name_ar: str,
        authorized_strength: int,
        orbat_unit_id: Optional[str] = None,
    ) -> UnitManning:
        unit_id = f"unit-{uuid.uuid4().hex[:10]}"
        unit = UnitManning(
            unit_id=unit_id,
            unit_name_en=unit_name_en,
            unit_name_ar=unit_name_ar,
            orbat_unit_id=orbat_unit_id,
            authorized_strength=int(authorized_strength),
            assigned_strength=0,
            slots=[],
        )
        self.units[unit_id] = unit
        return unit

    def add_slot(
        self,
        unit_id: str,
        position_title_en: str,
        position_title_ar: str,
        required_rank: Rank,
        required_mos: str,
        required_clearance: ClearanceLevel = ClearanceLevel.CONFIDENTIAL,
        required_certs: Optional[List[str]] = None,
    ) -> ManningSlot:
        unit = self.units[unit_id]
        slot = ManningSlot(
            slot_id=f"slot-{uuid.uuid4().hex[:12]}",
            unit_id=unit_id,
            position_title_en=position_title_en,
            position_title_ar=position_title_ar,
            required_rank=required_rank,
            required_mos=required_mos,
            required_clearance=required_clearance,
            required_certifications=list(required_certs or []),
            filled_by=None,
            status="vacant",
        )
        unit.slots.append(slot)
        self.slot_to_unit[slot.slot_id] = unit_id
        return slot

    def _member_meets_slot(self, member, slot: ManningSlot) -> Tuple[bool, str]:
        if Rank.rank_level(member.rank) < Rank.rank_level(slot.required_rank):
            return False, "rank below requirement"
        if slot.required_mos and member.mos != slot.required_mos:
            return False, "MOS mismatch"
        if ClearanceLevel.level(member.clearance) < ClearanceLevel.level(slot.required_clearance):
            return False, "clearance below requirement"
        if slot.required_certifications:
            member_certs = set(member.certifications or [])
            missing = [c for c in slot.required_certifications if c not in member_certs]
            if missing:
                return False, f"missing certifications: {', '.join(missing)}"
        return True, ""

    def fill_slot(self, slot_id: str, member_id: str) -> bool:
        unit_id = self.slot_to_unit.get(slot_id)
        if not unit_id:
            return False
        unit = self.units[unit_id]
        slot = next((s for s in unit.slots if s.slot_id == slot_id), None)
        if slot is None:
            return False
        member = self.personnel_registry.get_member(member_id) if self.personnel_registry else None
        if member is None:
            return False
        ok, _reason = self._member_meets_slot(member, slot)
        if not ok:
            return False
        if slot.filled_by is None:
            unit.assigned_strength += 1
        slot.filled_by = member_id
        slot.status = "filled"
        return True

    def vacate_slot(self, slot_id: str):
        unit_id = self.slot_to_unit.get(slot_id)
        if not unit_id:
            return
        unit = self.units[unit_id]
        slot = next((s for s in unit.slots if s.slot_id == slot_id), None)
        if slot is None:
            return
        if slot.filled_by is not None:
            unit.assigned_strength = max(0, unit.assigned_strength - 1)
        slot.filled_by = None
        slot.status = "vacant"

    def auto_fill(self, unit_id: str) -> dict:
        unit = self.units[unit_id]
        if self.personnel_registry is None:
            return {"filled": 0, "still_vacant": unit.vacant_count(), "no_match": []}
        pool = list(self.personnel_registry.get_members(unit_id=unit_id))
        assigned = {slot.filled_by for slot in unit.slots if slot.filled_by}
        available = [m for m in pool if m.member_id not in assigned]
        vacancies = [slot for slot in unit.slots if slot.is_vacant()]

        # Tactical priority: leadership continuity first.
        def _slot_priority(slot: ManningSlot):
            if Rank.is_officer(slot.required_rank):
                return 0
            if Rank.is_nco(slot.required_rank):
                return 1
            return 2

        vacancies.sort(key=_slot_priority)
        filled = 0
        no_match: List[str] = []
        for slot in vacancies:
            candidate = None
            for member in available:
                ok, _ = self._member_meets_slot(member, slot)
                if ok:
                    candidate = member
                    break
            if candidate is None:
                no_match.append(slot.slot_id)
                continue
            self.fill_slot(slot.slot_id, candidate.member_id)
            available = [m for m in available if m.member_id != candidate.member_id]
            filled += 1
        return {"filled": filled, "still_vacant": unit.vacant_count(), "no_match": no_match}

    def get_unit(self, unit_id: str) -> Optional[UnitManning]:
        return self.units.get(unit_id)

    def get_units(self) -> List[UnitManning]:
        return list(self.units.values())

    def get_fill_rates(self) -> Dict[str, float]:
        return {unit.unit_id: unit.fill_rate() for unit in self.units.values()}

    def get_critical_vacancies(self) -> List[dict]:
        rows = []
        for unit in self.units.values():
            for slot in unit.critical_vacancies():
                rows.append(
                    {
                        "unit_id": unit.unit_id,
                        "unit_name_en": unit.unit_name_en,
                        "slot_id": slot.slot_id,
                        "position_title_en": slot.position_title_en,
                        "required_rank": slot.required_rank.value,
                    }
                )
        return rows

    def create_from_orbat(self, orbat_unit_id: str) -> UnitManning:
        """
        Create unit slots from ORBAT metadata.

        If Phase 16 ORBAT manager is unavailable, we use deterministic defaults.
        """
        unit_name_en = f"ORBAT Unit {orbat_unit_id}"
        unit_name_ar = f"وحدة ORBAT {orbat_unit_id}"
        echelon = "company"
        try:
            from services.interop.msdl.orbat_manager import ORBATManager  # type: ignore

            manager = ORBATManager()
            maybe = manager.get_unit(orbat_unit_id)
            if maybe:
                unit_name_en = maybe.get("name_en", unit_name_en)
                unit_name_ar = maybe.get("name_ar", unit_name_ar)
                echelon = str(maybe.get("echelon", echelon)).lower()
        except Exception:
            pass

        counts = {"officer": 3, "nco": 6, "enlisted": 20}
        if echelon in {"battalion", "bn"}:
            counts = {"officer": 12, "nco": 20, "enlisted": 80}
        elif echelon in {"platoon"}:
            counts = {"officer": 1, "nco": 3, "enlisted": 12}
        auth = counts["officer"] + counts["nco"] + counts["enlisted"]
        unit = self.create_unit(unit_name_en=unit_name_en, unit_name_ar=unit_name_ar, authorized_strength=auth, orbat_unit_id=orbat_unit_id)

        for idx in range(counts["officer"]):
            self.add_slot(
                unit.unit_id,
                position_title_en=f"Officer Slot {idx+1}",
                position_title_ar=f"منصب ضابط {idx+1}",
                required_rank=Rank.CAPTAIN,
                required_mos="11A",
                required_clearance=ClearanceLevel.SECRET,
                required_certs=["S3M_WARGAMING_L1"],
            )
        for idx in range(counts["nco"]):
            self.add_slot(
                unit.unit_id,
                position_title_en=f"NCO Slot {idx+1}",
                position_title_ar=f"منصب صف ضابط {idx+1}",
                required_rank=Rank.SERGEANT,
                required_mos="11B",
                required_clearance=ClearanceLevel.CONFIDENTIAL,
                required_certs=[],
            )
        for idx in range(counts["enlisted"]):
            self.add_slot(
                unit.unit_id,
                position_title_en=f"Enlisted Slot {idx+1}",
                position_title_ar=f"منصب جندي {idx+1}",
                required_rank=Rank.CORPORAL,
                required_mos="11B",
                required_clearance=ClearanceLevel.CONFIDENTIAL,
                required_certs=[],
            )
        return unit

    def get_stats(self) -> dict:
        units = list(self.units.values())
        if not units:
            return {"total_units": 0, "total_slots": 0, "filled_slots": 0, "avg_fill_rate": 0.0}
        total_slots = sum(len(u.slots) for u in units)
        filled_slots = sum(len([s for s in u.slots if not s.is_vacant()]) for u in units)
        return {
            "total_units": len(units),
            "total_slots": total_slots,
            "filled_slots": filled_slots,
            "avg_fill_rate": round(sum(u.fill_rate() for u in units) / len(units), 4),
            "critical_vacancies": len(self.get_critical_vacancies()),
        }
