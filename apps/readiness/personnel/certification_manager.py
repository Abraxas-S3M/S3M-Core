"""Certification lifecycle manager for personnel readiness."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from apps.readiness.models import Certification, CertificationStatus


class CertificationManager:
    """Manages issuance, lifecycle, and requirement checks for certifications."""

    def __init__(self):
        self.certifications: Dict[str, Certification] = {}
        self.by_member: Dict[str, List[str]] = {}
        self._suspend_reasons: Dict[str, str] = {}
        self._revoke_reasons: Dict[str, str] = {}

    def issue_certification(
        self,
        member_id,
        certification_type,
        name_en,
        name_ar,
        issuing_authority,
        score=None,
        expiry_days=365,
        course_id=None,
        exercise_id=None,
    ) -> Certification:
        now = datetime.now(timezone.utc)
        cert = Certification(
            cert_id=f"CERT-{uuid.uuid4().hex[:10].upper()}",
            member_id=member_id,
            certification_type=str(certification_type),
            name_en=name_en,
            name_ar=name_ar,
            status=CertificationStatus.ACTIVE,
            issued_date=now,
            expiry_date=(now + timedelta(days=int(expiry_days))) if expiry_days else None,
            issuing_authority=issuing_authority,
            score=score,
            linked_course_id=course_id,
            linked_exercise_id=exercise_id,
        )
        self.certifications[cert.cert_id] = cert
        self.by_member.setdefault(member_id, []).append(cert.cert_id)
        return cert

    def renew(self, cert_id, new_expiry_days: int = 365):
        cert = self.certifications[cert_id]
        now = datetime.now(timezone.utc)
        cert.status = CertificationStatus.ACTIVE
        cert.expiry_date = now + timedelta(days=int(new_expiry_days))
        return cert

    def suspend(self, cert_id, reason: str):
        cert = self.certifications[cert_id]
        cert.status = CertificationStatus.SUSPENDED
        self._suspend_reasons[cert_id] = reason
        return cert

    def revoke(self, cert_id, reason: str):
        cert = self.certifications[cert_id]
        cert.status = CertificationStatus.REVOKED
        self._revoke_reasons[cert_id] = reason
        return cert

    def get_certification(self, cert_id) -> Optional[Certification]:
        return self.certifications.get(cert_id)

    def get_member_certifications(self, member_id) -> List[Certification]:
        ids = self.by_member.get(member_id, [])
        return [self.certifications[i] for i in ids if i in self.certifications]

    def get_expiring_soon(self, days: int = 30) -> List[Certification]:
        out: List[Certification] = []
        for cert in self.certifications.values():
            delta = cert.days_until_expiry()
            if delta is not None and 0 <= delta <= days:
                out.append(cert)
        return out

    def get_expired(self) -> List[Certification]:
        out: List[Certification] = []
        now = datetime.now(timezone.utc)
        for cert in self.certifications.values():
            if cert.expiry_date and cert.expiry_date <= now:
                if cert.status == CertificationStatus.ACTIVE:
                    cert.status = CertificationStatus.EXPIRED
                out.append(cert)
            elif cert.status == CertificationStatus.EXPIRED:
                out.append(cert)
        return out

    def check_requirements(self, member_id, required_certs: List[str]) -> dict:
        member_certs = self.get_member_certifications(member_id)
        active_by_type = {c.certification_type: c for c in member_certs}
        met: List[str] = []
        missing: List[str] = []
        expired: List[str] = []
        for cert_type in required_certs:
            cert = active_by_type.get(cert_type)
            if cert is None:
                missing.append(cert_type)
            elif cert.is_valid():
                met.append(cert_type)
            else:
                expired.append(cert_type)
        return {"met": met, "missing": missing, "expired": expired, "all_met": not missing and not expired}

    def sync_from_training_portal(self):
        """Optional Phase 18 bridge: sync completion data if training module exists."""
        try:
            # Repository-safe optional import; skip when Phase 18 package is absent.
            from apps.simulation.training import CourseManager, OfficerManager  # type: ignore
        except Exception:
            return {"synced": 0, "errors": 0, "source": "unavailable"}

        synced = 0
        errors = 0
        try:
            officer_mgr = OfficerManager()
            course_mgr = CourseManager()
            officers = getattr(officer_mgr, "list_officers", lambda: [])()
            courses = getattr(course_mgr, "list_courses", lambda: [])()
            course_map = {str(c.get("course_id", "")): c for c in courses if isinstance(c, dict)}
            for officer in officers:
                completed = officer.get("completed_courses", []) if isinstance(officer, dict) else []
                for course_id in completed:
                    if not course_id:
                        continue
                    course = course_map.get(str(course_id), {})
                    self.issue_certification(
                        member_id=str(officer.get("officer_id") or officer.get("member_id") or "UNKNOWN"),
                        certification_type=str(course.get("certification_type") or f"COURSE_{course_id}"),
                        name_en=str(course.get("name_en") or course.get("name") or "Course Completion"),
                        name_ar=str(course.get("name_ar") or "إكمال دورة"),
                        issuing_authority="S3M Training Center",
                        score=officer.get("latest_score"),
                        expiry_days=365,
                        course_id=str(course_id),
                        exercise_id=None,
                    )
                    synced += 1
        except Exception:
            errors += 1
        return {"synced": synced, "errors": errors, "source": "phase18"}

    def create_standard_cert_types(self) -> List[dict]:
        return [
            {"type": "S3M_WARGAMING_L1", "name_en": "Wargaming Operator Level 1", "name_ar": "مشغل ألعاب حربية مستوى 1"},
            {"type": "S3M_CYBER_DEFENDER", "name_en": "Cyber Defense Analyst", "name_ar": "محلل الدفاع السيبراني"},
            {"type": "S3M_MARITIME_WATCH", "name_en": "Maritime Watch Officer", "name_ar": "ضابط المراقبة البحرية"},
            {"type": "S3M_AUTONOMY_CMD", "name_en": "Autonomous Systems Commander", "name_ar": "قائد الأنظمة المستقلة"},
            {"type": "S3M_COALITION_COORD", "name_en": "Coalition Coordinator", "name_ar": "منسق التحالف"},
            {"type": "UAV_OPERATOR", "name_en": "UAV Operator", "name_ar": "مشغل طائرات بدون طيار"},
            {"type": "NBC_QUALIFIED", "name_en": "NBC Defense Qualified", "name_ar": "مؤهل دفاع كيميائي"},
            {"type": "COMBAT_MEDIC", "name_en": "Combat Medical Technician", "name_ar": "فني طبي قتالي"},
            {"type": "JUMPMASTER", "name_en": "Military Parachutist", "name_ar": "مظلي عسكري"},
            {"type": "SIGNALS_OPERATOR", "name_en": "Military Signals Operator", "name_ar": "مشغل إشارات عسكرية"},
        ]

    def get_stats(self) -> dict:
        total = len(self.certifications)
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for cert in self.certifications.values():
            by_status[cert.status.value] = by_status.get(cert.status.value, 0) + 1
            by_type[cert.certification_type] = by_type.get(cert.certification_type, 0) + 1
        return {
            "total": total,
            "expiring_30d": len(self.get_expiring_soon(30)),
            "expired": len(self.get_expired()),
            "by_status": by_status,
            "by_type": by_type,
            "members_with_certs": len(self.by_member),
        }
