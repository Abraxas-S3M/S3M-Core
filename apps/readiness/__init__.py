"""
S3M Layer 14 — Personnel & Readiness
Military personnel management, training certification, deployment eligibility,
unit manning, and bilingual Arabic/English HR.

THE FINAL LAYER of the 14-layer S3M sovereign military AI stack.

Subsystems:
- Personnel Registry: Service members with rank, MOS, clearance, medical, deployments
- Unit Manning: Tables of Organization (TO&E), fill rates, shortages
- Training & Certification: Military qualifications pipeline (extends Phase 18)
- Deployment Eligibility: Rule-based readiness checks for deployment suitability
- Readiness Scoring: Unit and individual readiness metrics
- Coalition Personnel: GCC partner force personnel interoperability
- HR Adapters: ERPNext, Odoo, OrangeHRM integration for existing HR systems

Data Flow:
  Personnel records → Eligibility engine → Unit readiness score
  Phase 18 training scores → Certification status → Eligibility
  Phase 16 ORBAT → Unit manning table → Fill rate → Readiness
  Phase 17 maintenance → Equipment readiness + Personnel readiness = Unit readiness
  → Dashboard (Layer 06) personnel readiness overlay
"""

from apps.readiness.coalition_bridge import CoalitionPersonnelBridge
from apps.readiness.hr_adapter import HRAdapter
from apps.readiness.manager import ReadinessManager
from apps.readiness.models import (
    Branch,
    Certification,
    CertificationStatus,
    ClearanceLevel,
    DeploymentEligibility,
    DeploymentRecord,
    EligibilityRule,
    ManningSlot,
    MedicalStatus,
    MilitaryStatus,
    Rank,
    ReadinessLevel,
    ReadinessScore,
    ServiceMember,
    UnitManning,
)
from apps.readiness.personnel import CertificationManager, PersonnelRegistry
from apps.readiness.readiness_calculator import ReadinessCalculator
from apps.readiness.units import EligibilityEngine, UnitManningManager

__all__ = [
    "ReadinessManager",
    "ServiceMember",
    "Rank",
    "Branch",
    "MilitaryStatus",
    "ClearanceLevel",
    "MedicalStatus",
    "Certification",
    "CertificationStatus",
    "UnitManning",
    "ManningSlot",
    "DeploymentRecord",
    "DeploymentEligibility",
    "EligibilityRule",
    "ReadinessScore",
    "ReadinessLevel",
    "PersonnelRegistry",
    "UnitManningManager",
    "CertificationManager",
    "EligibilityEngine",
    "ReadinessCalculator",
    "CoalitionPersonnelBridge",
    "HRAdapter",
]
