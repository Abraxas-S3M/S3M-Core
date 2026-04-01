"""Coalition personnel interoperability bridge for GCC partner forces."""

from __future__ import annotations

from typing import Dict, List, Optional


class CoalitionPersonnelBridge:
    """Maps partner personnel records into S3M coalition readiness views."""

    PARTNERS = {
        178: "Saudi Arabia",
        223: "United Arab Emirates",
        117: "Kuwait",
        16: "Bahrain",
        164: "Qatar",
        154: "Oman",
    }

    def __init__(self):
        self._partner_personnel: Dict[int, List[dict]] = {}
        self._equivalence_map: Dict[str, List[str]] = {
            "S3M_WARGAMING_L1": ["GCC_WARGAME_L1", "JOINT_SIM_OP_L1"],
            "S3M_CYBER_DEFENDER": ["NATIONAL_CYBER_DEFENDER", "GCC_CYBER_ANALYST"],
            "S3M_MARITIME_WATCH": ["MARITIME_WATCH_STANDARDS"],
            "S3M_AUTONOMY_CMD": ["AUTONOMOUS_SYSTEMS_COMMAND"],
            "S3M_COALITION_COORD": ["JOINT_COALITION_COORD"],
            "UAV_OPERATOR": ["UAS_OPERATOR", "DRONE_PILOT_MIL"],
            "NBC_QUALIFIED": ["CBRN_QUALIFIED", "NBC_DEFENSE_BASIC"],
            "COMBAT_MEDIC": ["FIELD_MEDIC", "TACTICAL_MEDICAL_TECH"],
            "JUMPMASTER": ["MIL_PARACHUTIST", "AIRBORNE_MASTER"],
            "SIGNALS_OPERATOR": ["MIL_SIGNALS_OP", "TACTICAL_COMMS_OPERATOR"],
        }

    def register_partner_personnel(self, partner_code: int, personnel: List[dict]) -> int:
        if partner_code not in self.PARTNERS:
            raise ValueError(f"Unsupported GCC partner code: {partner_code}")
        target = self._partner_personnel.setdefault(partner_code, [])
        for row in personnel:
            rec = dict(row)
            rec.setdefault("partner_code", partner_code)
            rec.setdefault("partner_name", self.PARTNERS[partner_code])
            rec.setdefault("member_id", rec.get("id", f"{partner_code}-{len(target)+1:05d}"))
            certs = rec.get("certifications", [])
            rec["certifications"] = list(certs) if isinstance(certs, list) else []
            rec.setdefault("interoperability_status", "pending")
            target.append(rec)
        return len(personnel)

    def get_coalition_roster(self, partner_code: Optional[int] = None) -> List[dict]:
        if partner_code is not None:
            return list(self._partner_personnel.get(partner_code, []))
        rows: List[dict] = []
        for records in self._partner_personnel.values():
            rows.extend(records)
        return rows

    def check_interoperability(self, member_id: str, required_certs: List[str]) -> dict:
        member = None
        for row in self.get_coalition_roster():
            if row.get("member_id") == member_id:
                member = row
                break
        if member is None:
            raise KeyError(f"Coalition member not found: {member_id}")

        held = set(member.get("certifications", []))
        equivalences: List[dict] = []
        gaps: List[str] = []
        for req in required_certs:
            accepted = {req, *self._equivalence_map.get(req, [])}
            match = sorted(held.intersection(accepted))
            if match:
                equivalences.append({"required": req, "matched": match[0], "accepted_set": sorted(accepted)})
            else:
                gaps.append(req)
        compatible = len(gaps) == 0
        member["interoperability_status"] = "compatible" if compatible else "gaps"
        return {"compatible": compatible, "equivalences": equivalences, "gaps": gaps}

    def get_coalition_readiness(self) -> dict:
        partners: List[dict] = []
        combined_strength = 0
        scores: List[float] = []

        for code, records in self._partner_personnel.items():
            strength = len(records)
            compatible = len([r for r in records if r.get("interoperability_status") == "compatible"])
            pending = len([r for r in records if r.get("interoperability_status") == "pending"])
            score = ((compatible + (0.5 * pending)) / strength * 100.0) if strength else 0.0
            partners.append(
                {
                    "partner_code": code,
                    "partner_name": self.PARTNERS.get(code, str(code)),
                    "strength": strength,
                    "interop_score": round(score, 2),
                }
            )
            combined_strength += strength
            if strength:
                scores.append(score)
        interop_score = sum(scores) / len(scores) if scores else 0.0
        return {
            "partners": partners,
            "combined_strength": combined_strength,
            "interop_score": round(interop_score, 2),
        }
