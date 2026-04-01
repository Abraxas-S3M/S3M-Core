"""Unit and force readiness scoring for Phase 20."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from apps.readiness.models import ReadinessLevel, ReadinessScore
from apps.readiness.personnel.certification_manager import CertificationManager
from apps.readiness.personnel.registry import PersonnelRegistry
from apps.readiness.units.eligibility_engine import EligibilityEngine
from apps.readiness.units.manning_manager import UnitManningManager


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReadinessCalculator:
    """Calculates personnel-centric and force-wide readiness summaries."""

    def __init__(
        self,
        personnel_registry: Optional[PersonnelRegistry] = None,
        manning_manager: Optional[UnitManningManager] = None,
        cert_manager: Optional[CertificationManager] = None,
        eligibility_engine: Optional[EligibilityEngine] = None,
    ) -> None:
        self.personnel_registry = personnel_registry or PersonnelRegistry()
        self.manning_manager = manning_manager or UnitManningManager(personnel_registry=self.personnel_registry)
        self.cert_manager = cert_manager or CertificationManager()
        self.eligibility_engine = eligibility_engine or EligibilityEngine()
        self.history: Dict[str, List[ReadinessScore]] = {}

    def _equipment_readiness(self, unit_id: str) -> float:
        # Tactical fallback: if Layer 11 fleet services are unavailable, use conservative default.
        try:
            from services.maintenance.assets.fleet_manager import FleetManager

            data = FleetManager().get_fleet_readiness()
            total_assets = int(data.get("total_assets", 0) or 0)
            if total_assets <= 0:
                return 75.0
            return float(data.get("readiness_pct", 75.0))
        except Exception:
            return 75.0

    def _readiness_level(self, score: float) -> ReadinessLevel:
        if score >= 80.0:
            return ReadinessLevel.GREEN
        if score >= 60.0:
            return ReadinessLevel.AMBER
        return ReadinessLevel.RED

    def calculate_unit_readiness(self, unit_id: str) -> ReadinessScore:
        unit = self.manning_manager.get_unit(unit_id)
        personnel = self.personnel_registry.get_unit_roster(unit_id)
        total = len(personnel)

        eligible_count = 0
        cert_complete = 0
        expired_count = 0
        medical_holds = 0
        for member in personnel:
            certs = self.cert_manager.get_member_certifications(member.member_id)
            eligibility = self.eligibility_engine.evaluate(member, certifications=certs)
            if eligibility.eligible:
                eligible_count += 1
            if all(cert.is_valid() for cert in certs) and certs:
                cert_complete += 1
            expired_count += len([c for c in certs if not c.is_valid()])
            if str(member.medical.value) != "FIT_FOR_DUTY":
                medical_holds += 1

        deployment_eligible_rate = (eligible_count / total) if total else 0.0
        personnel_readiness = deployment_eligible_rate * 100.0
        training_readiness = ((cert_complete / total) * 100.0) if total else 0.0
        equipment_readiness = self._equipment_readiness(unit_id)
        overall = (personnel_readiness * 0.40) + (training_readiness * 0.30) + (equipment_readiness * 0.30)
        level = self._readiness_level(overall)

        fill_rate = unit.fill_rate() if unit else 0.0
        critical_shortages = []
        if unit:
            for slot in unit.critical_vacancies():
                critical_shortages.append(f"Vacant {slot.required_rank.value} {slot.position_title_en}")
        if expired_count:
            critical_shortages.append(f"Expired certifications: {expired_count}")
        if medical_holds:
            critical_shortages.append(f"Medical holds: {medical_holds}")

        llm_prompt = (
            f"Assess readiness for {unit.unit_name_en if unit else unit_id}: "
            f"fill rate {fill_rate*100:.1f}%, cert rate {training_readiness:.1f}%, "
            f"equipment rate {equipment_readiness:.1f}%. Critical issues: {critical_shortages}. "
            "Provide: 1) Overall assessment 2) Risk areas 3) Priority actions to improve readiness."
        )
        llm_assessment = None
        try:
            from src.llm_core.inference import S3MInference

            llm_assessment = S3MInference().generate(llm_prompt, max_tokens=256)
        except Exception:
            llm_assessment = (
                f"Readiness assessment: level={level.value}. "
                f"Key gaps: {', '.join(critical_shortages) if critical_shortages else 'none'}."
            )

        score = ReadinessScore(
            unit_id=unit_id,
            timestamp=_utcnow(),
            personnel_readiness=round(personnel_readiness, 2),
            training_readiness=round(training_readiness, 2),
            equipment_readiness=round(equipment_readiness, 2),
            overall_readiness=round(overall, 2),
            readiness_level=level,
            manning_fill_rate=round(fill_rate * 100.0, 2),
            certification_rate=round(training_readiness, 2),
            deployment_eligible_rate=round(deployment_eligible_rate * 100.0, 2),
            critical_shortages=critical_shortages,
            expired_certifications=expired_count,
            llm_assessment=llm_assessment,
        )
        self.history.setdefault(unit_id, []).append(score)
        return score

    def calculate_force_readiness(self, unit_ids: Optional[List[str]] = None) -> dict:
        units = self.manning_manager.get_units()
        ids = unit_ids or [u.unit_id for u in units]
        rows = [self.calculate_unit_readiness(uid) for uid in ids]
        if not rows:
            return {
                "overall_readiness": 0.0,
                "readiness_level": ReadinessLevel.RED.value,
                "units": [],
                "force_green_pct": 0.0,
                "force_amber_pct": 0.0,
                "force_red_pct": 0.0,
            }
        avg = sum(r.overall_readiness for r in rows) / len(rows)
        green = len([r for r in rows if r.readiness_level == ReadinessLevel.GREEN])
        amber = len([r for r in rows if r.readiness_level == ReadinessLevel.AMBER])
        red = len([r for r in rows if r.readiness_level == ReadinessLevel.RED])
        return {
            "overall_readiness": round(avg, 2),
            "readiness_level": self._readiness_level(avg).value,
            "units": [r.to_dict() for r in rows],
            "force_green_pct": round((green / len(rows)) * 100.0, 2),
            "force_amber_pct": round((amber / len(rows)) * 100.0, 2),
            "force_red_pct": round((red / len(rows)) * 100.0, 2),
        }

    def get_readiness_trends(self, unit_id: str, days: int = 90) -> List[dict]:
        _ = days
        return [score.to_dict() for score in self.history.get(unit_id, [])]

    def generate_readiness_report(self, unit_id: Optional[str] = None) -> str:
        if unit_id:
            score = self.calculate_unit_readiness(unit_id)
            summary = (
                f"Unit readiness report (EN): {unit_id} overall {score.overall_readiness:.1f}% "
                f"{score.readiness_level.value}. Critical gaps: "
                f"{', '.join(score.critical_shortages) if score.critical_shortages else 'none'}.\n"
                f"تقرير الجاهزية (AR): الوحدة {unit_id} بمستوى {score.overall_readiness:.1f}% "
                f"({score.readiness_level.value})."
            )
            return summary
        force = self.calculate_force_readiness()
        return (
            f"Force readiness report (EN): overall {force['overall_readiness']:.1f}% "
            f"{force['readiness_level']}.\n"
            f"تقرير جاهزية القوة (AR): الجاهزية العامة {force['overall_readiness']:.1f}% "
            f"({force['readiness_level']})."
        )
