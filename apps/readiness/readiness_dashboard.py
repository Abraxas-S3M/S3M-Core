"""Readiness dashboard provider for personnel and unit manning views."""

from __future__ import annotations

from typing import Dict, List, Optional

from apps.readiness.models import ServiceMember


class ReadinessDashboardProvider:
    """Aggregates personnel readiness, manning, and coalition summaries."""

    def __init__(self, manager=None):
        self.manager = manager

    def bind(self, manager) -> None:
        self.manager = manager

    def _require_manager(self):
        if self.manager is None:
            raise RuntimeError("ReadinessDashboardProvider is not bound to a ReadinessManager")
        return self.manager

    def get_readiness_overview(self) -> dict:
        mgr = self._require_manager()
        personnel_stats = mgr.personnel_registry.get_statistics()
        units = mgr.unit_manning_manager.get_units()
        force = mgr.readiness_calculator.calculate_force_readiness([u.unit_id for u in units]) if units else {}
        expiring = mgr.certification_manager.get_expiring_soon(30)
        expired = mgr.certification_manager.get_expired()
        critical_vacancies = mgr.unit_manning_manager.get_critical_vacancies()
        coalition = mgr.coalition_bridge.get_coalition_readiness()

        units_summary = []
        for unit in units:
            score = mgr.readiness_calculator.calculate_unit_readiness(unit.unit_id)
            units_summary.append(
                {
                    "unit_id": unit.unit_id,
                    "name_en": unit.unit_name_en,
                    "name_ar": unit.unit_name_ar,
                    "fill_rate": round(unit.fill_rate() * 100.0, 2),
                    "readiness_level": score.readiness_level.value,
                    "strength": {"authorized": unit.authorized_strength, "assigned": unit.assigned_strength},
                }
            )

        return {
            "total_personnel": personnel_stats["total"],
            "deployable": personnel_stats["deployable"],
            "deployable_pct": personnel_stats["deployable_pct"],
            "by_branch": personnel_stats["by_branch"],
            "by_rank_group": {
                "officers": personnel_stats["officers"],
                "ncos": personnel_stats["ncos"],
                "enlisted": personnel_stats["enlisted"],
            },
            "by_status": personnel_stats["by_status"],
            "units": units_summary,
            "expiring_certs_30d": len(expiring),
            "expired_certs": len(expired),
            "critical_vacancies": len(critical_vacancies),
            "overall_readiness": round(float(force.get("overall_readiness", 0.0)), 2),
            "readiness_level": str(force.get("readiness_level", "BLACK")),
            "coalition_partners": len(coalition.get("partners", [])),
        }

    def get_unit_detail(self, unit_id: str) -> dict:
        mgr = self._require_manager()
        unit = mgr.unit_manning_manager.get_unit(unit_id)
        if unit is None:
            raise KeyError(f"Unit not found: {unit_id}")

        roster = [member.to_safe_dict() for member in mgr.personnel_registry.get_unit_roster(unit_id)]
        cert_status = []
        for member in mgr.personnel_registry.get_unit_roster(unit_id):
            certs = mgr.certification_manager.get_member_certifications(member.member_id)
            cert_status.append(
                {
                    "member_id": member.member_id,
                    "name_en": member.name_en,
                    "name_ar": member.name_ar,
                    "active": len([c for c in certs if c.is_valid()]),
                    "expired": len([c for c in certs if not c.is_valid()]),
                }
            )

        readiness = mgr.readiness_calculator.calculate_unit_readiness(unit_id)
        return {
            "unit": unit.to_dict(),
            "roster": roster,
            "manning_table": [slot.to_dict() for slot in unit.slots],
            "fill_rate": round(unit.fill_rate() * 100.0, 2),
            "vacancies": unit.vacant_count(),
            "critical_vacancies": [slot.to_dict() for slot in unit.critical_vacancies()],
            "readiness_score": readiness.to_dict(),
            "cert_status": cert_status,
        }

    def get_member_profile(self, member_id: str) -> dict:
        mgr = self._require_manager()
        member = mgr.personnel_registry.get_member(member_id)
        if member is None:
            raise KeyError(f"Member not found: {member_id}")
        certs = mgr.certification_manager.get_member_certifications(member_id)
        eligibility = mgr.eligibility_engine.evaluate(member=member, certifications=certs, deployments=[])
        return {
            "member": member.to_safe_dict(),
            "certifications": [cert.to_dict() for cert in certs],
            "deployments": [],
            "eligibility": eligibility.to_dict(),
            "training_score": member.training_score,
        }

    def get_manning_board(self) -> List[dict]:
        mgr = self._require_manager()
        board = []
        for unit in mgr.unit_manning_manager.get_units():
            critical = unit.critical_vacancies()
            board.append(
                {
                    "unit_id": unit.unit_id,
                    "name_en": unit.unit_name_en,
                    "name_ar": unit.unit_name_ar,
                    "authorized": unit.authorized_strength,
                    "assigned": unit.assigned_strength,
                    "fill_rate": round(unit.fill_rate() * 100.0, 2),
                    "vacancies": unit.vacant_count(),
                    "critical_shortages": [slot.position_title_en for slot in critical],
                }
            )
        return board
