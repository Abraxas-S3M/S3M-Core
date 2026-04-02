# File: src/doctrine/doctrine_models.py
"""Typed models for the S3M sovereign doctrine configuration layer.

A DoctrineProfile captures the operational preferences, escalation
tolerances, intelligence biasing rules, and reporting styles for a
specific deployment.  Every field is explicit, serialisable, and
auditable — there are no hidden personality hacks.

Doctrine influences HOW the system interprets and presents intelligence.
It never fabricates, suppresses, or overwrites raw evidence.

Hierarchy:
  DoctrineProfile
    ├── EngagementPolicy       — rules of engagement and escalation
    ├── IntelligenceBiasPolicy — domain priorities and corroboration rules
    ├── ReportingPolicy        — output style and detail level
    ├── ConfidenceAdjustmentPolicy — threshold tuning
    └── RegionContext          — geographic and operational context
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# =====================================================================
# Enums
# =====================================================================

class EscalationTolerance(Enum):
    """How aggressively the system flags escalation."""
    VERY_CONSERVATIVE = "very_conservative"  # flag early, many alerts
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    PERMISSIVE = "permissive"
    VERY_PERMISSIVE = "very_permissive"      # flag late, few alerts


class ReportingDetail(Enum):
    """Output detail level for reporting."""
    EXECUTIVE_SUMMARY = "executive_summary"   # 2-3 sentence high-level
    OPERATOR_BRIEF = "operator_brief"         # key facts + recommended actions
    ANALYST_DETAIL = "analyst_detail"         # full technical breakdown


class AlertingMode(Enum):
    """How the system surfaces alerts."""
    ALL_EVENTS = "all_events"
    THRESHOLD_ONLY = "threshold_only"
    CORROBORATED_ONLY = "corroborated_only"


class DomainPriority(Enum):
    """Relative priority for an intelligence domain."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    SUPPRESSED = "suppressed"


# =====================================================================
# Engagement Policy
# =====================================================================

@dataclass
class EngagementPolicy:
    """Rules of engagement and escalation tolerance.

    Controls how the system interprets threat levels and when it
    recommends escalation to human operators.
    """
    escalation_tolerance: EscalationTolerance = EscalationTolerance.BALANCED
    auto_escalate_threat_levels: List[str] = field(
        default_factory=lambda: ["critical"]
    )
    require_human_approval_above: str = "high"
    weapons_posture: str = "weapons_tight"  # weapons_tight, weapons_free, weapons_hold
    max_autonomy_level: int = 3            # 1-5, where 5 = full autonomy
    rules: List[str] = field(default_factory=lambda: [
        "All engagements require positive identification",
        "Civilian proximity requires commander approval",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "escalation_tolerance": self.escalation_tolerance.value,
            "auto_escalate_threat_levels": list(self.auto_escalate_threat_levels),
            "require_human_approval_above": self.require_human_approval_above,
            "weapons_posture": self.weapons_posture,
            "max_autonomy_level": self.max_autonomy_level,
            "rules": list(self.rules),
        }


# =====================================================================
# Intelligence Bias Policy
# =====================================================================

@dataclass
class IntelligenceBiasPolicy:
    """Policy-driven intelligence domain priorities and corroboration rules.

    This controls WHICH signals the system pays most attention to, and
    how many independent sources must agree before a finding is surfaced.
    It never suppresses raw data — only adjusts scoring weights.
    """
    domain_priorities: Dict[str, DomainPriority] = field(default_factory=lambda: {
        "cyber": DomainPriority.NORMAL,
        "maritime": DomainPriority.NORMAL,
        "airspace": DomainPriority.NORMAL,
        "ground": DomainPriority.NORMAL,
        "osint": DomainPriority.NORMAL,
        "sigint": DomainPriority.NORMAL,
        "geoint": DomainPriority.NORMAL,
    })
    min_corroboration_sources: int = 1     # how many sources must agree
    require_multi_domain_for_critical: bool = True
    suppress_unverified_osint: bool = False
    pattern_match_weight_multiplier: float = 1.0  # boost/reduce pattern weight
    threat_genome_weight_multiplier: float = 1.0

    def get_priority_multiplier(self, domain: str) -> float:
        """Return a scoring multiplier for a domain based on its priority."""
        priority = self.domain_priorities.get(domain.lower(), DomainPriority.NORMAL)
        return {
            DomainPriority.CRITICAL: 1.5,
            DomainPriority.HIGH: 1.25,
            DomainPriority.NORMAL: 1.0,
            DomainPriority.LOW: 0.75,
            DomainPriority.SUPPRESSED: 0.3,
        }[priority]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_priorities": {k: v.value for k, v in self.domain_priorities.items()},
            "min_corroboration_sources": self.min_corroboration_sources,
            "require_multi_domain_for_critical": self.require_multi_domain_for_critical,
            "suppress_unverified_osint": self.suppress_unverified_osint,
            "pattern_match_weight_multiplier": self.pattern_match_weight_multiplier,
            "threat_genome_weight_multiplier": self.threat_genome_weight_multiplier,
        }


# =====================================================================
# Reporting Policy
# =====================================================================

@dataclass
class ReportingPolicy:
    """Output style preferences for intelligence products.

    Controls how much detail the system includes in its outputs and
    which sections are emphasized.
    """
    detail_level: ReportingDetail = ReportingDetail.OPERATOR_BRIEF
    alerting_mode: AlertingMode = AlertingMode.THRESHOLD_ONLY
    include_uncertainty_notes: bool = True
    include_raw_scores: bool = False
    include_methodology: bool = False
    include_alternative_hypotheses: bool = True
    include_historical_context: bool = True
    max_hypotheses_in_report: int = 3
    language_preference: str = "en"       # "en", "ar", "bilingual"
    classification_marking: str = "UNCLASSIFIED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detail_level": self.detail_level.value,
            "alerting_mode": self.alerting_mode.value,
            "include_uncertainty_notes": self.include_uncertainty_notes,
            "include_raw_scores": self.include_raw_scores,
            "include_methodology": self.include_methodology,
            "include_alternative_hypotheses": self.include_alternative_hypotheses,
            "max_hypotheses_in_report": self.max_hypotheses_in_report,
            "language_preference": self.language_preference,
            "classification_marking": self.classification_marking,
        }


# =====================================================================
# Confidence Adjustment Policy
# =====================================================================

@dataclass
class ConfidenceAdjustmentPolicy:
    """Policy-driven confidence threshold tuning.

    Adjusts the thresholds at which predictions and detections are
    surfaced, without changing the raw scores themselves.
    """
    alert_confidence_threshold: float = 0.5
    prediction_confidence_floor: float = 0.1
    genome_match_threshold: float = 0.3
    escalation_confidence_threshold: float = 0.7
    conservative_factor: float = 1.0       # >1 = more conservative, <1 = more permissive
    # Per-domain threshold overrides
    domain_thresholds: Dict[str, float] = field(default_factory=dict)

    def get_effective_threshold(self, base: float, domain: str = "") -> float:
        """Apply the conservative factor and any domain override."""
        if domain and domain.lower() in self.domain_thresholds:
            return self.domain_thresholds[domain.lower()]
        return min(0.99, base * self.conservative_factor)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_confidence_threshold": self.alert_confidence_threshold,
            "prediction_confidence_floor": self.prediction_confidence_floor,
            "genome_match_threshold": self.genome_match_threshold,
            "escalation_confidence_threshold": self.escalation_confidence_threshold,
            "conservative_factor": self.conservative_factor,
            "domain_thresholds": dict(self.domain_thresholds),
        }


# =====================================================================
# Region Context
# =====================================================================

@dataclass
class RegionContext:
    """Geographic and operational context for doctrine."""
    region_name: str = "default"
    theater: str = ""                       # e.g., "Arabian Gulf", "Red Sea"
    operating_environment: str = "peacetime"  # peacetime, heightened, conflict
    priority_threat_actors: List[str] = field(default_factory=list)
    priority_threat_domains: List[str] = field(default_factory=list)
    geographic_bounds: Optional[Dict[str, float]] = None  # lat/lon bounds
    time_zone: str = "UTC+03:00"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_name": self.region_name,
            "theater": self.theater,
            "operating_environment": self.operating_environment,
            "priority_threat_actors": list(self.priority_threat_actors),
            "priority_threat_domains": list(self.priority_threat_domains),
            "time_zone": self.time_zone,
        }


# =====================================================================
# Doctrine Profile (top-level container)
# =====================================================================

@dataclass
class DoctrineProfile:
    """Complete sovereign doctrine configuration for a deployment.

    This is the top-level configuration object.  It packages all
    sub-policies into a single, versioned, auditable profile that
    can be loaded from a config file, switched at runtime, and
    serialised for compliance records.
    """
    profile_id: str = ""
    name: str = "default"
    version: str = "1.0"
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

    # Sub-policies
    engagement: EngagementPolicy = field(default_factory=EngagementPolicy)
    intelligence_bias: IntelligenceBiasPolicy = field(default_factory=IntelligenceBiasPolicy)
    reporting: ReportingPolicy = field(default_factory=ReportingPolicy)
    confidence: ConfidenceAdjustmentPolicy = field(default_factory=ConfidenceAdjustmentPolicy)
    region: RegionContext = field(default_factory=RegionContext)

    # Active flag
    active: bool = False

    def __post_init__(self) -> None:
        if not self.profile_id:
            self.profile_id = f"doc-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "active": self.active,
            "engagement": self.engagement.to_dict(),
            "intelligence_bias": self.intelligence_bias.to_dict(),
            "reporting": self.reporting.to_dict(),
            "confidence": self.confidence.to_dict(),
            "region": self.region.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DoctrineProfile":
        """Construct a profile from a configuration dictionary.

        Supports partial dicts — missing keys use defaults.
        """
        eng_data = data.get("engagement", {})
        engagement = EngagementPolicy(
            escalation_tolerance=EscalationTolerance(eng_data.get("escalation_tolerance", "balanced")),
            auto_escalate_threat_levels=eng_data.get("auto_escalate_threat_levels", ["critical"]),
            require_human_approval_above=eng_data.get("require_human_approval_above", "high"),
            weapons_posture=eng_data.get("weapons_posture", "weapons_tight"),
            max_autonomy_level=int(eng_data.get("max_autonomy_level", 3)),
            rules=eng_data.get("rules", []),
        )

        bias_data = data.get("intelligence_bias", {})
        dp_raw = bias_data.get("domain_priorities", {})
        domain_priorities = {
            k: DomainPriority(v) if isinstance(v, str) else v
            for k, v in dp_raw.items()
        }
        intel_bias = IntelligenceBiasPolicy(
            domain_priorities=domain_priorities,
            min_corroboration_sources=int(bias_data.get("min_corroboration_sources", 1)),
            require_multi_domain_for_critical=bias_data.get("require_multi_domain_for_critical", True),
            suppress_unverified_osint=bias_data.get("suppress_unverified_osint", False),
            pattern_match_weight_multiplier=float(bias_data.get("pattern_match_weight_multiplier", 1.0)),
            threat_genome_weight_multiplier=float(bias_data.get("threat_genome_weight_multiplier", 1.0)),
        )

        rep_data = data.get("reporting", {})
        reporting = ReportingPolicy(
            detail_level=ReportingDetail(rep_data.get("detail_level", "operator_brief")),
            alerting_mode=AlertingMode(rep_data.get("alerting_mode", "threshold_only")),
            include_uncertainty_notes=rep_data.get("include_uncertainty_notes", True),
            include_raw_scores=rep_data.get("include_raw_scores", False),
            include_methodology=rep_data.get("include_methodology", False),
            include_alternative_hypotheses=rep_data.get("include_alternative_hypotheses", True),
            max_hypotheses_in_report=int(rep_data.get("max_hypotheses_in_report", 3)),
            language_preference=rep_data.get("language_preference", "en"),
            classification_marking=rep_data.get("classification_marking", "UNCLASSIFIED"),
        )

        conf_data = data.get("confidence", {})
        confidence = ConfidenceAdjustmentPolicy(
            alert_confidence_threshold=float(conf_data.get("alert_confidence_threshold", 0.5)),
            prediction_confidence_floor=float(conf_data.get("prediction_confidence_floor", 0.1)),
            genome_match_threshold=float(conf_data.get("genome_match_threshold", 0.3)),
            escalation_confidence_threshold=float(conf_data.get("escalation_confidence_threshold", 0.7)),
            conservative_factor=float(conf_data.get("conservative_factor", 1.0)),
            domain_thresholds=conf_data.get("domain_thresholds", {}),
        )

        reg_data = data.get("region", {})
        region = RegionContext(
            region_name=reg_data.get("region_name", "default"),
            theater=reg_data.get("theater", ""),
            operating_environment=reg_data.get("operating_environment", "peacetime"),
            priority_threat_actors=reg_data.get("priority_threat_actors", []),
            priority_threat_domains=reg_data.get("priority_threat_domains", []),
            time_zone=reg_data.get("time_zone", "UTC+03:00"),
        )

        return cls(
            profile_id=data.get("profile_id", ""),
            name=data.get("name", "default"),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            created_by=data.get("created_by", "system"),
            engagement=engagement,
            intelligence_bias=intel_bias,
            reporting=reporting,
            confidence=confidence,
            region=region,
            active=data.get("active", False),
        )
