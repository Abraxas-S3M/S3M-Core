"""Core models for S3M Phase 20 personnel and readiness layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


class Branch(str, Enum):
    ARMY = "ARMY"
    AIR_FORCE = "AIR_FORCE"
    NAVY = "NAVY"
    ROYAL_GUARD = "ROYAL_GUARD"
    SPECIAL_FORCES = "SPECIAL_FORCES"
    CYBER = "CYBER"
    LOGISTICS = "LOGISTICS"
    MEDICAL = "MEDICAL"
    INTELLIGENCE = "INTELLIGENCE"
    JOINT = "JOINT"


class Rank(str, Enum):
    PRIVATE = "PRIVATE"
    CORPORAL = "CORPORAL"
    SERGEANT = "SERGEANT"
    STAFF_SERGEANT = "STAFF_SERGEANT"
    FIRST_SERGEANT = "FIRST_SERGEANT"
    SERGEANT_MAJOR = "SERGEANT_MAJOR"
    SECOND_LIEUTENANT = "SECOND_LIEUTENANT"
    FIRST_LIEUTENANT = "FIRST_LIEUTENANT"
    CAPTAIN = "CAPTAIN"
    MAJOR = "MAJOR"
    LIEUTENANT_COLONEL = "LIEUTENANT_COLONEL"
    COLONEL = "COLONEL"
    BRIGADIER_GENERAL = "BRIGADIER_GENERAL"
    MAJOR_GENERAL = "MAJOR_GENERAL"
    LIEUTENANT_GENERAL = "LIEUTENANT_GENERAL"
    GENERAL = "GENERAL"

    @classmethod
    def rank_level(cls, rank: "Rank") -> int:
        order = {
            cls.PRIVATE: 1,
            cls.CORPORAL: 2,
            cls.SERGEANT: 3,
            cls.STAFF_SERGEANT: 4,
            cls.FIRST_SERGEANT: 5,
            cls.SERGEANT_MAJOR: 6,
            cls.SECOND_LIEUTENANT: 7,
            cls.FIRST_LIEUTENANT: 8,
            cls.CAPTAIN: 9,
            cls.MAJOR: 10,
            cls.LIEUTENANT_COLONEL: 11,
            cls.COLONEL: 12,
            cls.BRIGADIER_GENERAL: 13,
            cls.MAJOR_GENERAL: 14,
            cls.LIEUTENANT_GENERAL: 15,
            cls.GENERAL: 16,
        }
        return order[cls(rank)]

    @classmethod
    def is_officer(cls, rank: "Rank") -> bool:
        return cls.rank_level(cls(rank)) >= cls.rank_level(cls.SECOND_LIEUTENANT)

    @classmethod
    def is_nco(cls, rank: "Rank") -> bool:
        lvl = cls.rank_level(cls(rank))
        return cls.rank_level(cls.SERGEANT) <= lvl <= cls.rank_level(cls.SERGEANT_MAJOR)

    @classmethod
    def is_enlisted(cls, rank: "Rank") -> bool:
        return cls.rank_level(cls(rank)) <= cls.rank_level(cls.CORPORAL)


class MilitaryStatus(str, Enum):
    ACTIVE_DUTY = "ACTIVE_DUTY"
    RESERVE = "RESERVE"
    DEPLOYED = "DEPLOYED"
    TRAINING = "TRAINING"
    MEDICAL_LEAVE = "MEDICAL_LEAVE"
    ADMINISTRATIVE_LEAVE = "ADMINISTRATIVE_LEAVE"
    RETIRED = "RETIRED"
    SEPARATED = "SEPARATED"


class ClearanceLevel(str, Enum):
    UNCLASSIFIED = "UNCLASSIFIED"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP_SECRET"
    SCI = "SCI"

    @classmethod
    def level(cls, clearance: "ClearanceLevel") -> int:
        order = {
            cls.UNCLASSIFIED: 0,
            cls.CONFIDENTIAL: 1,
            cls.SECRET: 2,
            cls.TOP_SECRET: 3,
            cls.SCI: 4,
        }
        return order[cls(clearance)]


class MedicalStatus(str, Enum):
    FIT_FOR_DUTY = "FIT_FOR_DUTY"
    LIMITED_DUTY = "LIMITED_DUTY"
    TEMPORARY_DISABILITY = "TEMPORARY_DISABILITY"
    PERMANENT_DISABILITY = "PERMANENT_DISABILITY"
    PENDING_EVALUATION = "PENDING_EVALUATION"


@dataclass
class ServiceMember:
    member_id: str
    service_number: str
    name_en: str
    name_ar: str
    rank: Rank
    branch: Branch
    mos: str
    mos_description_en: str
    mos_description_ar: str
    status: MilitaryStatus
    clearance: ClearanceLevel
    medical: MedicalStatus
    unit_id: str
    unit_name_en: str
    unit_name_ar: str
    date_of_rank: datetime
    service_start_date: datetime
    years_of_service: float
    certifications: List[str] = field(default_factory=list)
    deployments: List[str] = field(default_factory=list)
    training_score: Optional[float] = None
    eligible_for_deployment: bool = True
    next_evaluation_date: Optional[datetime] = None
    languages: List[str] = field(default_factory=lambda: ["ar", "en"])
    specializations: List[str] = field(default_factory=list)
    contact: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rank = Rank(self.rank)
        self.branch = Branch(self.branch)
        self.status = MilitaryStatus(self.status)
        self.clearance = ClearanceLevel(self.clearance)
        self.medical = MedicalStatus(self.medical)
        self.date_of_rank = _dt(self.date_of_rank) or _utcnow()
        self.service_start_date = _dt(self.service_start_date) or _utcnow()
        self.next_evaluation_date = _dt(self.next_evaluation_date)
        if self.years_of_service <= 0:
            self.years_of_service = max(
                0.0, (_utcnow() - self.service_start_date).total_seconds() / (365.25 * 86400.0)
            )
        self.years_of_service = float(self.years_of_service)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def to_safe_dict(self) -> Dict[str, Any]:
        # Tactical privacy guard: never expose personal contact payloads to dashboards/logs.
        row = self.to_dict()
        row.pop("contact", None)
        row["contact_redacted"] = True
        return row

    def is_deployable(self) -> bool:
        return (
            self.status == MilitaryStatus.ACTIVE_DUTY
            and self.medical == MedicalStatus.FIT_FOR_DUTY
            and ClearanceLevel.level(self.clearance) >= ClearanceLevel.level(ClearanceLevel.CONFIDENTIAL)
            and self.eligible_for_deployment
        )

    def is_officer(self) -> bool:
        return Rank.is_officer(self.rank)

    def time_in_grade_months(self) -> float:
        return max(0.0, (_utcnow() - self.date_of_rank).total_seconds() / (30.4375 * 86400.0))


class CertificationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    PENDING_RENEWAL = "PENDING_RENEWAL"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


@dataclass
class Certification:
    cert_id: str
    member_id: str
    certification_type: str
    name_en: str
    name_ar: str
    status: CertificationStatus
    issued_date: datetime
    expiry_date: Optional[datetime]
    issuing_authority: str
    score: Optional[float] = None
    linked_course_id: Optional[str] = None
    linked_exercise_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.status = CertificationStatus(self.status)
        self.issued_date = _dt(self.issued_date) or _utcnow()
        self.expiry_date = _dt(self.expiry_date)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def is_valid(self) -> bool:
        if self.status != CertificationStatus.ACTIVE:
            return False
        if self.expiry_date is None:
            return True
        return self.expiry_date > _utcnow()

    def days_until_expiry(self) -> Optional[float]:
        if self.expiry_date is None:
            return None
        return (self.expiry_date - _utcnow()).total_seconds() / 86400.0


@dataclass
class ManningSlot:
    slot_id: str
    unit_id: str
    position_title_en: str
    position_title_ar: str
    required_rank: Rank
    required_mos: str
    required_clearance: ClearanceLevel
    required_certifications: List[str] = field(default_factory=list)
    filled_by: Optional[str] = None
    status: str = "vacant"

    def __post_init__(self) -> None:
        self.required_rank = Rank(self.required_rank)
        self.required_clearance = ClearanceLevel(self.required_clearance)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def is_vacant(self) -> bool:
        return self.filled_by is None or self.status == "vacant"


@dataclass
class UnitManning:
    unit_id: str
    unit_name_en: str
    unit_name_ar: str
    orbat_unit_id: Optional[str]
    authorized_strength: int
    assigned_strength: int
    slots: List[ManningSlot] = field(default_factory=list)
    commander_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def fill_rate(self) -> float:
        if self.authorized_strength <= 0:
            return 0.0
        return min(1.0, max(0.0, self.assigned_strength / float(self.authorized_strength)))

    def vacant_count(self) -> int:
        return len([slot for slot in self.slots if slot.is_vacant()])

    def critical_vacancies(self) -> List[ManningSlot]:
        critical = []
        for slot in self.slots:
            if not slot.is_vacant():
                continue
            if Rank.is_officer(slot.required_rank) or Rank.is_nco(slot.required_rank):
                critical.append(slot)
        return critical


@dataclass
class DeploymentRecord:
    deployment_id: str
    member_id: str
    deployment_name: str
    location: str
    start_date: datetime
    end_date: Optional[datetime]
    status: str
    role: str
    unit_id: str

    def __post_init__(self) -> None:
        self.start_date = _dt(self.start_date) or _utcnow()
        self.end_date = _dt(self.end_date)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    def duration_days(self) -> Optional[float]:
        if self.end_date is None:
            return None
        return max(0.0, (self.end_date - self.start_date).total_seconds() / 86400.0)

    def is_active(self) -> bool:
        return self.status.lower() == "active"


@dataclass
class DeploymentEligibility:
    member_id: str
    eligible: bool
    checks: List[dict]
    overall_readiness: str
    disqualifiers: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class EligibilityRule:
    name: str
    check: str
    weight: float
    mandatory: bool

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


class ReadinessLevel(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    BLACK = "BLACK"


@dataclass
class ReadinessScore:
    unit_id: str
    timestamp: datetime
    personnel_readiness: float
    training_readiness: float
    equipment_readiness: float
    overall_readiness: float
    readiness_level: ReadinessLevel
    manning_fill_rate: float
    certification_rate: float
    deployment_eligible_rate: float
    critical_shortages: List[str] = field(default_factory=list)
    expired_certifications: int = 0
    llm_assessment: Optional[str] = None

    def __post_init__(self) -> None:
        self.timestamp = _dt(self.timestamp) or _utcnow()
        self.readiness_level = ReadinessLevel(self.readiness_level)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))


# Re-export targets are declared in apps/readiness/__init__.py.
