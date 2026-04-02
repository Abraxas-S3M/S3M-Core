# File: src/doctrine/doctrine_profile_manager.py
"""Doctrine profile management: load, store, validate, switch, audit.

The manager maintains a library of named doctrine profiles and tracks
which one is active.  Every profile switch is logged to an audit trail
so compliance officers can reconstruct what policy was in effect at
any point in time.

Usage::

    manager = DoctrineProfileManager()
    manager.register_builtin_profiles()      # seed with Saudi/GCC defaults
    manager.activate("saudi_gulf_defensive")
    active = manager.get_active()
    manager.activate("heightened_readiness")  # switch logged
    log = manager.get_audit_log()
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .doctrine_models import (
    AlertingMode,
    ConfidenceAdjustmentPolicy,
    DoctrineProfile,
    DomainPriority,
    EngagementPolicy,
    EscalationTolerance,
    IntelligenceBiasPolicy,
    RegionContext,
    ReportingDetail,
    ReportingPolicy,
)


# =====================================================================
# Audit entry
# =====================================================================

@dataclass
class DoctrineAuditEntry:
    """Audit log entry for doctrine changes."""
    entry_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = ""               # "activated", "deactivated", "registered", "removed"
    profile_id: str = ""
    profile_name: str = ""
    previous_profile_id: Optional[str] = None
    previous_profile_name: Optional[str] = None
    actor: str = "system"          # who made the change
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"audit-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "previous_profile_id": self.previous_profile_id,
            "previous_profile_name": self.previous_profile_name,
            "actor": self.actor,
            "reason": self.reason,
        }


# =====================================================================
# Profile Manager
# =====================================================================

class DoctrineProfileManager:
    """Manages a library of doctrine profiles with activation and audit."""

    def __init__(self) -> None:
        self._profiles: Dict[str, DoctrineProfile] = {}
        self._by_name: Dict[str, str] = {}
        self._active_id: Optional[str] = None
        self._audit_log: List[DoctrineAuditEntry] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, profile: DoctrineProfile, actor: str = "system") -> str:
        """Register a profile. Returns profile_id."""
        self._profiles[profile.profile_id] = profile
        self._by_name[profile.name.lower()] = profile.profile_id
        self._log_audit("registered", profile, actor=actor)
        return profile.profile_id

    def register_from_dict(self, data: Dict[str, Any], actor: str = "system") -> str:
        """Register a profile from a configuration dictionary."""
        profile = DoctrineProfile.from_dict(data)
        return self.register(profile, actor=actor)

    def remove(self, name_or_id: str, actor: str = "system") -> bool:
        """Remove a profile. Cannot remove the active profile."""
        pid = self._resolve(name_or_id)
        if pid is None:
            return False
        if pid == self._active_id:
            return False
        profile = self._profiles.pop(pid, None)
        if profile:
            self._by_name.pop(profile.name.lower(), None)
            self._log_audit("removed", profile, actor=actor)
            return True
        return False

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, name_or_id: str) -> Optional[DoctrineProfile]:
        pid = self._resolve(name_or_id)
        return self._profiles.get(pid) if pid else None

    def get_active(self) -> Optional[DoctrineProfile]:
        """Return the currently active doctrine profile."""
        if self._active_id:
            return self._profiles.get(self._active_id)
        return None

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Return summary of all registered profiles."""
        return [
            {
                "profile_id": p.profile_id,
                "name": p.name,
                "version": p.version,
                "active": p.profile_id == self._active_id,
                "escalation_tolerance": p.engagement.escalation_tolerance.value,
                "detail_level": p.reporting.detail_level.value,
                "region": p.region.region_name,
            }
            for p in self._profiles.values()
        ]

    def count(self) -> int:
        return len(self._profiles)

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self, name_or_id: str, actor: str = "system",
                 reason: str = "") -> bool:
        """Activate a profile by name or ID. Logs the switch."""
        pid = self._resolve(name_or_id)
        if pid is None or pid not in self._profiles:
            return False

        prev_profile = self.get_active()

        # Deactivate current
        if self._active_id and self._active_id in self._profiles:
            self._profiles[self._active_id].active = False

        # Activate new
        self._active_id = pid
        self._profiles[pid].active = True

        entry = DoctrineAuditEntry(
            action="activated",
            profile_id=pid,
            profile_name=self._profiles[pid].name,
            previous_profile_id=prev_profile.profile_id if prev_profile else None,
            previous_profile_name=prev_profile.name if prev_profile else None,
            actor=actor,
            reason=reason,
        )
        self._audit_log.append(entry)
        return True

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def get_audit_log(self, last_n: int = 50) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._audit_log[-last_n:]]

    # ------------------------------------------------------------------
    # Built-in profiles
    # ------------------------------------------------------------------

    def register_builtin_profiles(self) -> int:
        """Register standard Saudi/GCC doctrine profiles. Returns count."""
        profiles = [
            DoctrineProfile(
                name="saudi_gulf_defensive",
                version="1.0",
                description="Default Saudi defensive posture for Gulf theater operations",
                engagement=EngagementPolicy(
                    escalation_tolerance=EscalationTolerance.CONSERVATIVE,
                    auto_escalate_threat_levels=["critical"],
                    require_human_approval_above="high",
                    weapons_posture="weapons_tight",
                    max_autonomy_level=2,
                    rules=[
                        "Positive identification required before classification above MEDIUM",
                        "Civilian proximity requires commander override",
                        "Maritime threats in territorial waters auto-escalate",
                    ],
                ),
                intelligence_bias=IntelligenceBiasPolicy(
                    domain_priorities={
                        "maritime": DomainPriority.HIGH,
                        "airspace": DomainPriority.HIGH,
                        "cyber": DomainPriority.NORMAL,
                        "osint": DomainPriority.LOW,
                        "sigint": DomainPriority.HIGH,
                        "ground": DomainPriority.NORMAL,
                        "geoint": DomainPriority.NORMAL,
                    },
                    min_corroboration_sources=2,
                    require_multi_domain_for_critical=True,
                    pattern_match_weight_multiplier=1.2,
                ),
                reporting=ReportingPolicy(
                    detail_level=ReportingDetail.OPERATOR_BRIEF,
                    include_uncertainty_notes=True,
                    include_alternative_hypotheses=True,
                    max_hypotheses_in_report=3,
                    language_preference="bilingual",
                    classification_marking="RESTRICTED",
                ),
                confidence=ConfidenceAdjustmentPolicy(
                    alert_confidence_threshold=0.55,
                    escalation_confidence_threshold=0.75,
                    conservative_factor=1.15,
                ),
                region=RegionContext(
                    region_name="Arabian Gulf",
                    theater="CENTCOM AOR",
                    operating_environment="peacetime",
                    priority_threat_actors=["Houthi", "IRGC-Navy", "Unknown-UAV"],
                    priority_threat_domains=["maritime", "airspace", "cyber"],
                    time_zone="UTC+03:00",
                ),
            ),
            DoctrineProfile(
                name="heightened_readiness",
                version="1.0",
                description="Heightened readiness profile for elevated threat periods",
                engagement=EngagementPolicy(
                    escalation_tolerance=EscalationTolerance.VERY_CONSERVATIVE,
                    auto_escalate_threat_levels=["critical", "high"],
                    require_human_approval_above="medium",
                    weapons_posture="weapons_tight",
                    max_autonomy_level=3,
                ),
                intelligence_bias=IntelligenceBiasPolicy(
                    domain_priorities={
                        "maritime": DomainPriority.CRITICAL,
                        "airspace": DomainPriority.CRITICAL,
                        "cyber": DomainPriority.HIGH,
                        "sigint": DomainPriority.CRITICAL,
                        "osint": DomainPriority.NORMAL,
                        "ground": DomainPriority.HIGH,
                        "geoint": DomainPriority.HIGH,
                    },
                    min_corroboration_sources=1,
                    require_multi_domain_for_critical=False,
                    pattern_match_weight_multiplier=1.5,
                    threat_genome_weight_multiplier=1.3,
                ),
                reporting=ReportingPolicy(
                    detail_level=ReportingDetail.ANALYST_DETAIL,
                    alerting_mode=AlertingMode.ALL_EVENTS,
                    include_raw_scores=True,
                    include_methodology=True,
                    max_hypotheses_in_report=5,
                    language_preference="bilingual",
                    classification_marking="SECRET",
                ),
                confidence=ConfidenceAdjustmentPolicy(
                    alert_confidence_threshold=0.35,
                    escalation_confidence_threshold=0.55,
                    conservative_factor=0.85,
                ),
                region=RegionContext(
                    region_name="Arabian Gulf",
                    theater="CENTCOM AOR",
                    operating_environment="heightened",
                    priority_threat_actors=["Houthi", "IRGC-Navy", "Unknown-UAV"],
                    priority_threat_domains=["maritime", "airspace", "cyber"],
                ),
            ),
            DoctrineProfile(
                name="executive_overview",
                version="1.0",
                description="Minimal-detail profile for senior leadership briefings",
                engagement=EngagementPolicy(
                    escalation_tolerance=EscalationTolerance.BALANCED,
                ),
                reporting=ReportingPolicy(
                    detail_level=ReportingDetail.EXECUTIVE_SUMMARY,
                    alerting_mode=AlertingMode.CORROBORATED_ONLY,
                    include_uncertainty_notes=False,
                    include_raw_scores=False,
                    include_methodology=False,
                    include_alternative_hypotheses=False,
                    max_hypotheses_in_report=1,
                    language_preference="en",
                ),
                confidence=ConfidenceAdjustmentPolicy(
                    alert_confidence_threshold=0.7,
                    conservative_factor=1.3,
                ),
            ),
        ]
        for p in profiles:
            self.register(p)
        return len(profiles)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve(self, name_or_id: str) -> Optional[str]:
        """Resolve a name or ID to a profile ID."""
        if name_or_id in self._profiles:
            return name_or_id
        return self._by_name.get(name_or_id.lower())

    def _log_audit(self, action: str, profile: DoctrineProfile,
                   actor: str = "system") -> None:
        self._audit_log.append(DoctrineAuditEntry(
            action=action,
            profile_id=profile.profile_id,
            profile_name=profile.name,
            actor=actor,
        ))
