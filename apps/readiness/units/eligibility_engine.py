"""Deployment eligibility rules engine for personnel readiness."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from apps.readiness.models import (
    Certification,
    CertificationStatus,
    DeploymentEligibility,
    DeploymentRecord,
    EligibilityRule,
    MedicalStatus,
    MilitaryStatus,
    ServiceMember,
)
from src.llm_core.inference import S3MInference


class EligibilityEngine:
    """Evaluate member and unit deployment eligibility with weighted rules."""

    def __init__(self):
        self._rules: List[EligibilityRule] = [
            EligibilityRule("active_duty", "status == ACTIVE_DUTY", 1.0, True),
            EligibilityRule("medical_fit", "medical == FIT_FOR_DUTY", 1.0, True),
            EligibilityRule("clearance_valid", "clearance >= CONFIDENTIAL", 0.8, True),
            EligibilityRule("no_pending_evaluation", "medical != PENDING_EVALUATION", 0.5, False),
            EligibilityRule("time_since_last_deployment", "days_since_last_deployment > 180", 0.6, False),
            EligibilityRule("training_current", "no_expired_certifications", 0.7, False),
            EligibilityRule("min_time_in_grade", "time_in_grade_months > 6", 0.3, False),
        ]

    def add_rule(self, name: str, check: str, weight: float, mandatory: bool) -> None:
        self.remove_rule(name)
        self._rules.append(EligibilityRule(name=name, check=check, weight=float(weight), mandatory=bool(mandatory)))

    def remove_rule(self, name: str) -> None:
        self._rules = [rule for rule in self._rules if rule.name != name]

    def get_rules(self) -> List[dict]:
        return [rule.to_dict() for rule in self._rules]

    @staticmethod
    def _days_since_last_deployment(deployments: Optional[List[DeploymentRecord]]) -> float:
        if not deployments:
            return 3650.0
        records = sorted(
            [d for d in deployments if d.start_date is not None],
            key=lambda d: d.start_date,
            reverse=True,
        )
        if not records:
            return 3650.0
        last = records[0]
        end = last.end_date or last.start_date
        return max(0.0, (datetime.now(timezone.utc) - end).total_seconds() / 86400.0)

    def evaluate(
        self,
        member: ServiceMember,
        certifications: Optional[List[Certification]] = None,
        deployments: Optional[List[DeploymentRecord]] = None,
    ) -> DeploymentEligibility:
        certifications = certifications or []
        deployments = deployments or []

        expired_count = len([cert for cert in certifications if cert.status == CertificationStatus.EXPIRED or not cert.is_valid()])
        days_since_last = self._days_since_last_deployment(deployments)
        tig_months = member.time_in_grade_months()

        checks: List[dict] = []
        disqualifiers: List[str] = []
        recommendations: List[str] = []

        optional_total = 0.0
        optional_pass = 0.0
        mandatory_failed = False

        for rule in self._rules:
            passed = True
            detail = "passed"
            if rule.name == "active_duty":
                passed = member.status == MilitaryStatus.ACTIVE_DUTY
                if not passed:
                    detail = f"status is {member.status.value}"
            elif rule.name == "medical_fit":
                passed = member.medical == MedicalStatus.FIT_FOR_DUTY
                if not passed:
                    detail = f"medical status is {member.medical.value}"
            elif rule.name == "clearance_valid":
                passed = member.clearance.value in {"CONFIDENTIAL", "SECRET", "TOP_SECRET", "SCI"}
                if not passed:
                    detail = f"clearance is {member.clearance.value}"
            elif rule.name == "no_pending_evaluation":
                passed = member.medical != MedicalStatus.PENDING_EVALUATION
                if not passed:
                    detail = "pending medical evaluation"
            elif rule.name == "time_since_last_deployment":
                passed = days_since_last > 180.0
                if not passed:
                    detail = f"only {days_since_last:.1f} days since last deployment"
            elif rule.name == "training_current":
                passed = expired_count == 0
                if not passed:
                    detail = f"{expired_count} expired certifications"
            elif rule.name == "min_time_in_grade":
                passed = tig_months > 6.0
                if not passed:
                    detail = f"time in grade {tig_months:.1f} months"

            checks.append({"rule": rule.name, "passed": bool(passed), "detail": detail})
            if rule.mandatory and not passed:
                mandatory_failed = True
                disqualifiers.append(rule.name)
                recommendations.append(f"Resolve mandatory check: {rule.name}.")
            if not rule.mandatory:
                optional_total += rule.weight
                if passed:
                    optional_pass += rule.weight
                else:
                    recommendations.append(f"Improve readiness factor: {rule.name}.")

        if mandatory_failed:
            readiness = "red"
            eligible = False
        elif optional_total > 0 and optional_pass < optional_total:
            readiness = "amber"
            eligible = True
        else:
            readiness = "green"
            eligible = True

        return DeploymentEligibility(
            member_id=member.member_id,
            eligible=eligible,
            checks=checks,
            overall_readiness=readiness,
            disqualifiers=sorted(set(disqualifiers)),
            recommendations=sorted(set(recommendations)),
        )

    def evaluate_unit(self, unit_id: str, personnel: List[ServiceMember]) -> dict:
        rows = [member for member in personnel if member.unit_id == unit_id]
        if not rows:
            return {
                "unit_id": unit_id,
                "total": 0,
                "green": 0,
                "amber": 0,
                "red": 0,
                "eligible_pct": 0.0,
                "disqualifier_summary": {},
            }
        evaluations = [self.evaluate(member) for member in rows]
        greens = len([row for row in evaluations if row.overall_readiness == "green"])
        ambers = len([row for row in evaluations if row.overall_readiness == "amber"])
        reds = len([row for row in evaluations if row.overall_readiness == "red"])
        eligible = len([row for row in evaluations if row.eligible])
        disq = Counter()
        for row in evaluations:
            disq.update(row.disqualifiers)
        return {
            "unit_id": unit_id,
            "total": len(rows),
            "green": greens,
            "amber": ambers,
            "red": reds,
            "eligible_pct": round((eligible / len(rows)) * 100.0, 2),
            "disqualifier_summary": dict(disq),
        }

    def generate_eligibility_report(self, member: ServiceMember, eligibility: DeploymentEligibility) -> str:
        checks_summary = "; ".join(
            f"{row['rule']}={'PASS' if row['passed'] else 'FAIL'} ({row['detail']})"
            for row in eligibility.checks
        )
        prompt = (
            f"Generate a military deployment eligibility report for {member.rank.value} {member.name_en}: "
            f"{checks_summary}. Include: eligibility status, disqualifiers, recommended actions to achieve full readiness."
        )
        try:
            english = S3MInference().generate(prompt, max_tokens=320)
        except Exception:
            english = (
                f"Eligibility Report (EN)\nMember: {member.rank.value} {member.name_en}\n"
                f"Eligibility: {'ELIGIBLE' if eligibility.eligible else 'NOT ELIGIBLE'} ({eligibility.overall_readiness.upper()})\n"
                f"Disqualifiers: {', '.join(eligibility.disqualifiers) if eligibility.disqualifiers else 'None'}\n"
                f"Actions: {', '.join(eligibility.recommendations) if eligibility.recommendations else 'Maintain standards'}"
            )

        # Tactical bilingual fallback keeps command and HR staffs synchronized.
        arabic = (
            "تقرير الجاهزية للانتشار (AR)\n"
            f"العسكري: {member.name_ar}\n"
            f"الحالة: {'مؤهل' if eligibility.eligible else 'غير مؤهل'} ({eligibility.overall_readiness})\n"
            f"الأسباب: {', '.join(eligibility.disqualifiers) if eligibility.disqualifiers else 'لا يوجد'}\n"
            f"الإجراءات: {', '.join(eligibility.recommendations) if eligibility.recommendations else 'الاستمرار على الجاهزية'}"
        )
        return f"{english}\n\n{arabic}"
