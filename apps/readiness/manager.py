"""Central orchestrator for S3M Phase 20 Personnel & Readiness."""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from apps.readiness.coalition_bridge import CoalitionPersonnelBridge
from apps.readiness.hr_adapter import HRAdapter
from apps.readiness.models import (
    Branch,
    Certification,
    ClearanceLevel,
    DeploymentEligibility,
    MedicalStatus,
    MilitaryStatus,
    Rank,
    ReadinessScore,
    ServiceMember,
)
from apps.readiness.personnel.certification_manager import CertificationManager
from apps.readiness.personnel.registry import PersonnelRegistry
from apps.readiness.readiness_calculator import ReadinessCalculator
from apps.readiness.readiness_dashboard import ReadinessDashboardProvider
from apps.readiness.units.eligibility_engine import EligibilityEngine
from apps.readiness.units.manning_manager import UnitManningManager


class ReadinessManager:
    """High-level façade for personnel, eligibility, and unit readiness workflows."""

    def __init__(self) -> None:
        self.personnel_registry = PersonnelRegistry()
        self.certification_manager = CertificationManager()
        self.unit_manning_manager = UnitManningManager(personnel_registry=self.personnel_registry)
        self.eligibility_engine = EligibilityEngine()
        self.readiness_calculator = ReadinessCalculator(
            personnel_registry=self.personnel_registry,
            manning_manager=self.unit_manning_manager,
            cert_manager=self.certification_manager,
            eligibility_engine=self.eligibility_engine,
        )
        self.coalition_bridge = CoalitionPersonnelBridge()
        self.hr_adapter = HRAdapter(backend="standalone")
        self.dashboard_provider = ReadinessDashboardProvider(manager=self)

    def register_member(
        self,
        name_en: str,
        name_ar: str,
        rank: Rank,
        branch: Branch,
        mos: str,
        mos_description_en: str,
        mos_description_ar: str,
        unit_id: str,
        unit_name_en: str,
        unit_name_ar: str,
        service_number: Optional[str] = None,
        clearance: ClearanceLevel = ClearanceLevel.CONFIDENTIAL,
        medical: MedicalStatus = MedicalStatus.FIT_FOR_DUTY,
        languages: Optional[List[str]] = None,
        specializations: Optional[List[str]] = None,
    ) -> ServiceMember:
        return self.personnel_registry.register(
            name_en=name_en,
            name_ar=name_ar,
            rank=rank,
            branch=branch,
            mos=mos,
            mos_description_en=mos_description_en,
            mos_description_ar=mos_description_ar,
            unit_id=unit_id,
            unit_name_en=unit_name_en,
            unit_name_ar=unit_name_ar,
            service_number=service_number,
            clearance=clearance,
            medical=medical,
            languages=languages,
            specializations=specializations,
        )

    def get_member(self, member_id: str) -> Optional[ServiceMember]:
        return self.personnel_registry.get_member(member_id)

    def search(self, query: str) -> List[ServiceMember]:
        return self.personnel_registry.search(query)

    def update_status(self, member_id: str, status: MilitaryStatus) -> ServiceMember:
        return self.personnel_registry.update_status(member_id, status)

    def update_medical(self, member_id: str, medical: MedicalStatus) -> ServiceMember:
        return self.personnel_registry.update_medical(member_id, medical)

    def update_clearance(self, member_id: str, clearance: ClearanceLevel) -> ServiceMember:
        return self.personnel_registry.update_clearance(member_id, clearance)

    def promote(self, member_id: str, rank: Rank) -> ServiceMember:
        return self.personnel_registry.promote(member_id, rank)

    def issue_certification(
        self,
        member_id: str,
        certification_type: str,
        name_en: str,
        name_ar: str,
        issuing_authority: str,
        score: Optional[float] = None,
        expiry_days: int = 365,
        course_id: Optional[str] = None,
        exercise_id: Optional[str] = None,
    ) -> Certification:
        cert = self.certification_manager.issue_certification(
            member_id=member_id,
            certification_type=certification_type,
            name_en=name_en,
            name_ar=name_ar,
            issuing_authority=issuing_authority,
            score=score,
            expiry_days=expiry_days,
            course_id=course_id,
            exercise_id=exercise_id,
        )
        member = self.personnel_registry.get_member(member_id)
        if member and cert.cert_id not in member.certifications:
            member.certifications.append(cert.cert_id)
        return cert

    def get_certifications(self, member_id: str) -> List[Certification]:
        return self.certification_manager.get_member_certifications(member_id)

    def check_cert_requirements(self, member_id: str, certs: List[str]) -> dict:
        return self.certification_manager.check_requirements(member_id, certs)

    def create_unit(
        self,
        unit_name_en: str,
        unit_name_ar: str,
        authorized_strength: int,
        orbat_unit_id: Optional[str] = None,
    ):
        return self.unit_manning_manager.create_unit(
            unit_name_en=unit_name_en,
            unit_name_ar=unit_name_ar,
            authorized_strength=authorized_strength,
            orbat_unit_id=orbat_unit_id,
        )

    def fill_slot(self, slot_id: str, member_id: str) -> bool:
        return self.unit_manning_manager.fill_slot(slot_id, member_id)

    def auto_fill(self, unit_id: str) -> dict:
        return self.unit_manning_manager.auto_fill(unit_id)

    def evaluate_eligibility(self, member_id: str) -> DeploymentEligibility:
        member = self.personnel_registry.get_member(member_id)
        if not member:
            raise KeyError(f"member not found: {member_id}")
        certs = self.certification_manager.get_member_certifications(member_id)
        return self.eligibility_engine.evaluate(member=member, certifications=certs)

    def calculate_readiness(self, unit_id: str) -> ReadinessScore:
        return self.readiness_calculator.calculate_unit_readiness(unit_id)

    def calculate_force_readiness(self) -> dict:
        return self.readiness_calculator.calculate_force_readiness()

    def get_readiness_overview(self) -> dict:
        return self.dashboard_provider.get_readiness_overview()

    def get_unit_detail(self, unit_id: str) -> dict:
        return self.dashboard_provider.get_unit_detail(unit_id)

    def get_member_profile(self, member_id: str) -> dict:
        return self.dashboard_provider.get_member_profile(member_id)

    def get_manning_board(self) -> List[dict]:
        return self.dashboard_provider.get_manning_board()

    def register_coalition_personnel(self, partner_code: int, personnel: List[dict]) -> int:
        return self.coalition_bridge.register_partner_personnel(partner_code, personnel)

    def generate_readiness_report(self, unit_id: Optional[str] = None) -> str:
        return self.readiness_calculator.generate_readiness_report(unit_id=unit_id)

    def generate_manning_report(self) -> str:
        board = self.dashboard_provider.get_manning_board()
        lines_en = ["S3M Manning Assessment", f"Units evaluated: {len(board)}"]
        lines_ar = ["تقييم التشكيل البشري", f"عدد الوحدات المقيمة: {len(board)}"]
        for row in board:
            lines_en.append(
                f"- {row['name_en']}: fill {row['fill_rate']}%, vacancies {row['vacancies']}, "
                f"critical {len(row['critical_shortages'])}"
            )
            lines_ar.append(
                f"- {row['name_ar']}: نسبة الشغل {row['fill_rate']}٪، شواغر {row['vacancies']}، "
                f"شواغر حرجة {len(row['critical_shortages'])}"
            )
        return "\n".join(lines_en + ["", "--- Arabic / العربية ---"] + lines_ar)

    def create_saudi_battalion(self) -> dict:
        members = self.personnel_registry.create_saudi_battalion_template()
        if not members:
            return {"personnel": 0, "unit": "", "fill_rate": 0.0}

        unit_id = members[0].unit_id
        unit_en = members[0].unit_name_en
        unit_ar = members[0].unit_name_ar

        unit = self.unit_manning_manager.create_unit(
            unit_name_en=unit_en,
            unit_name_ar=unit_ar,
            authorized_strength=45,
            orbat_unit_id=f"orbat_{unit_id}",
        )
        for member in members:
            self.personnel_registry.assign_to_unit(member.member_id, unit.unit_id, unit_en, unit_ar)
            req_rank = member.rank if not Rank.is_officer(member.rank) else Rank.CAPTAIN
            self.unit_manning_manager.add_slot(
                unit.unit_id,
                "Operator",
                "مشغل",
                required_rank=req_rank,
                required_mos=member.mos,
            )

        self.auto_fill(unit.unit_id)

        for idx, member in enumerate(members):
            if idx < 30:
                self.issue_certification(
                    member_id=member.member_id,
                    certification_type="S3M_WARGAMING_L1",
                    name_en="Wargaming Operator Level 1",
                    name_ar="مشغل ألعاب حربية مستوى 1",
                    issuing_authority="S3M Training Center",
                )
            if idx < 20:
                self.issue_certification(
                    member_id=member.member_id,
                    certification_type="UAV_OPERATOR",
                    name_en="UAV Operator",
                    name_ar="مشغل طائرات بدون طيار",
                    issuing_authority="Saudi MOD",
                )
            if idx < 5:
                cert = self.issue_certification(
                    member_id=member.member_id,
                    certification_type="S3M_CYBER_DEFENDER",
                    name_en="Cyber Defense Analyst",
                    name_ar="محلل الدفاع السيبراني",
                    issuing_authority="S3M Cyber Academy",
                )
                cert.expiry_date = cert.issued_date - timedelta(days=1) if idx < 3 else cert.expiry_date

        return {
            "personnel": len(members),
            "unit": unit.unit_id,
            "fill_rate": round(self.unit_manning_manager.get_unit(unit.unit_id).fill_rate() * 100.0, 2),
        }

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "personnel_registry": self.personnel_registry.get_statistics(),
            "certification_manager": self.certification_manager.get_stats(),
            "unit_manning_manager": self.unit_manning_manager.get_stats(),
            "eligibility_engine": {"rules": len(self.eligibility_engine.get_rules())},
            "readiness_calculator": {
                "history_points": len(self.readiness_calculator.history),
                "configured": True,
            },
            "coalition_bridge": self.coalition_bridge.get_coalition_readiness(),
            "hr_adapter": self.hr_adapter.get_erp_status(),
        }
