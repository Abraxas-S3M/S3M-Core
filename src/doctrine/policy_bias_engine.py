# File: src/doctrine/policy_bias_engine.py
"""Policy bias engine — applies doctrine to scoring and presentation.

CRITICAL DESIGN PRINCIPLE: Doctrine influences interpretation and
presentation of intelligence.  It NEVER fabricates, suppresses, or
overwrites raw evidence.  Every adjustment is logged and reversible.

The engine takes a raw score/assessment and returns an adjusted version
plus an audit record showing exactly what changed and why.

Usage::

    engine = PolicyBiasEngine(doctrine_profile)
    adjusted = engine.apply_confidence_bias(raw_score=0.6, domain="maritime")
    # adjusted.adjusted_score > 0.6 if maritime is HIGH priority
    # adjusted.adjustments has the full audit trail

    report = engine.format_for_reporting(hypotheses, raw_evidence)
    # detail level depends on doctrine.reporting.detail_level
"""

from __future__ import annotations

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
    ReportingDetail,
    ReportingPolicy,
)


# =====================================================================
# Adjustment record (audit trail)
# =====================================================================

@dataclass
class PolicyAdjustment:
    """One logged adjustment applied by the policy engine."""
    adjustment_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    adjustment_type: str = ""       # "confidence_bias", "threshold_change", "priority_boost"
    field_name: str = ""
    raw_value: float = 0.0
    adjusted_value: float = 0.0
    doctrine_rule: str = ""         # which policy caused this
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.adjustment_id:
            self.adjustment_id = f"adj-{uuid.uuid4().hex[:6]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adjustment_id": self.adjustment_id,
            "timestamp": self.timestamp.isoformat(),
            "type": self.adjustment_type,
            "field": self.field_name,
            "raw": round(self.raw_value, 4),
            "adjusted": round(self.adjusted_value, 4),
            "rule": self.doctrine_rule,
            "explanation": self.explanation,
        }


@dataclass
class BiasResult:
    """Result of applying a doctrine bias to a score or assessment."""
    raw_value: float = 0.0
    adjusted_value: float = 0.0
    adjustments: List[PolicyAdjustment] = field(default_factory=list)
    doctrine_profile_name: str = ""
    doctrine_profile_id: str = ""

    @property
    def was_adjusted(self) -> bool:
        return abs(self.adjusted_value - self.raw_value) > 0.001

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_value": round(self.raw_value, 4),
            "adjusted_value": round(self.adjusted_value, 4),
            "was_adjusted": self.was_adjusted,
            "doctrine_profile": self.doctrine_profile_name,
            "adjustments": [a.to_dict() for a in self.adjustments],
        }


@dataclass
class FormattedReport:
    """A report formatted according to doctrine reporting policy."""
    detail_level: str = ""
    classification: str = ""
    sections: List[Dict[str, Any]] = field(default_factory=list)
    suppressed_fields: List[str] = field(default_factory=list)
    language: str = "en"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detail_level": self.detail_level,
            "classification": self.classification,
            "language": self.language,
            "section_count": len(self.sections),
            "suppressed_fields": list(self.suppressed_fields),
            "sections": list(self.sections),
        }


# =====================================================================
# Policy bias engine
# =====================================================================

class PolicyBiasEngine:
    """Applies active doctrine to scoring and reporting decisions.

    Every adjustment is logged.  Raw evidence is never overwritten.
    """

    def __init__(self, profile: Optional[DoctrineProfile] = None) -> None:
        self._profile = profile
        self._adjustment_log: List[PolicyAdjustment] = []

    @property
    def profile(self) -> Optional[DoctrineProfile]:
        return self._profile

    def set_profile(self, profile: DoctrineProfile) -> None:
        self._profile = profile

    # ------------------------------------------------------------------
    # Confidence biasing
    # ------------------------------------------------------------------

    def apply_confidence_bias(
        self,
        raw_score: float,
        domain: str = "",
        source_count: int = 1,
        is_critical: bool = False,
    ) -> BiasResult:
        """Apply doctrine-driven confidence adjustments.

        The raw score is PRESERVED in the result.  The adjusted score
        reflects doctrine priorities and thresholds.
        """
        if self._profile is None:
            return BiasResult(raw_value=raw_score, adjusted_value=raw_score)

        adjustments: List[PolicyAdjustment] = []
        score = raw_score
        bias = self._profile.intelligence_bias
        conf = self._profile.confidence

        # 1. Domain priority multiplier
        if domain:
            mult = bias.get_priority_multiplier(domain)
            if abs(mult - 1.0) > 0.01:
                old_score = score
                score = min(0.99, score * mult)
                adj = PolicyAdjustment(
                    adjustment_type="domain_priority",
                    field_name="confidence",
                    raw_value=old_score,
                    adjusted_value=score,
                    doctrine_rule=f"domain_priority[{domain}]={bias.domain_priorities.get(domain.lower(), 'normal')}",
                    explanation=f"Domain '{domain}' has priority multiplier {mult:.2f}",
                )
                adjustments.append(adj)
                self._adjustment_log.append(adj)

        # 2. Conservative factor
        if abs(conf.conservative_factor - 1.0) > 0.01:
            old_score = score
            # Conservative factor > 1 makes the system require higher raw scores
            # by scaling down the adjusted score
            if conf.conservative_factor > 1.0:
                score = score / conf.conservative_factor
            else:
                score = min(0.99, score / conf.conservative_factor)
            score = max(0.01, min(0.99, score))
            adj = PolicyAdjustment(
                adjustment_type="conservative_factor",
                field_name="confidence",
                raw_value=old_score,
                adjusted_value=score,
                doctrine_rule=f"conservative_factor={conf.conservative_factor}",
                explanation=(
                    "Conservative factor increases threshold requirements"
                    if conf.conservative_factor > 1.0
                    else "Permissive factor lowers threshold requirements"
                ),
            )
            adjustments.append(adj)
            self._adjustment_log.append(adj)

        # 3. Corroboration check
        if source_count < bias.min_corroboration_sources:
            old_score = score
            penalty = 0.85 ** (bias.min_corroboration_sources - source_count)
            score = score * penalty
            adj = PolicyAdjustment(
                adjustment_type="corroboration_penalty",
                field_name="confidence",
                raw_value=old_score,
                adjusted_value=score,
                doctrine_rule=f"min_corroboration_sources={bias.min_corroboration_sources}",
                explanation=f"Only {source_count} source(s) vs required {bias.min_corroboration_sources}",
            )
            adjustments.append(adj)
            self._adjustment_log.append(adj)

        # 4. Multi-domain requirement for critical
        if is_critical and bias.require_multi_domain_for_critical and source_count < 2:
            old_score = score
            score = score * 0.7
            adj = PolicyAdjustment(
                adjustment_type="multi_domain_requirement",
                field_name="confidence",
                raw_value=old_score,
                adjusted_value=score,
                doctrine_rule="require_multi_domain_for_critical=True",
                explanation="Critical assessment requires multi-domain corroboration",
            )
            adjustments.append(adj)
            self._adjustment_log.append(adj)

        return BiasResult(
            raw_value=raw_score,
            adjusted_value=round(max(0.01, min(0.99, score)), 4),
            adjustments=adjustments,
            doctrine_profile_name=self._profile.name,
            doctrine_profile_id=self._profile.profile_id,
        )

    # ------------------------------------------------------------------
    # Threshold checking
    # ------------------------------------------------------------------

    def should_alert(self, confidence: float, domain: str = "") -> bool:
        """Check if a confidence score exceeds the alert threshold."""
        if self._profile is None:
            return confidence >= 0.5
        threshold = self._profile.confidence.get_effective_threshold(
            self._profile.confidence.alert_confidence_threshold, domain,
        )
        return confidence >= threshold

    def should_escalate(self, confidence: float, threat_level: str = "") -> bool:
        """Check if an assessment should be escalated to humans."""
        if self._profile is None:
            return threat_level in ("critical", "high") and confidence >= 0.7
        eng = self._profile.engagement
        if threat_level in eng.auto_escalate_threat_levels:
            return True
        threshold = self._profile.confidence.escalation_confidence_threshold
        return confidence >= threshold

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    def format_for_reporting(
        self,
        hypotheses: List[Dict[str, Any]],
        raw_evidence: Optional[Dict[str, Any]] = None,
        entity_summary: Optional[Dict[str, Any]] = None,
    ) -> FormattedReport:
        """Format prediction/assessment output according to reporting policy.

        Different detail levels produce different amounts of information.
        Raw evidence is ALWAYS preserved in the output at analyst level.
        """
        if self._profile is None:
            return FormattedReport(
                detail_level="operator_brief",
                sections=[{"type": "hypotheses", "content": hypotheses}],
            )

        rep = self._profile.reporting
        sections: List[Dict[str, Any]] = []
        suppressed: List[str] = []

        # Limit hypotheses
        display_hyps = hypotheses[:rep.max_hypotheses_in_report]

        if rep.detail_level == ReportingDetail.EXECUTIVE_SUMMARY:
            # Minimal: just the dominant hypothesis summary
            if display_hyps:
                top = display_hyps[0]
                sections.append({
                    "type": "summary",
                    "content": f"Primary assessment: {top.get('label', 'unknown')} "
                               f"(confidence: {top.get('probability', 0):.0%})",
                })
            suppressed.extend(["raw_scores", "methodology", "uncertainty_notes",
                               "alternative_hypotheses"])

        elif rep.detail_level == ReportingDetail.OPERATOR_BRIEF:
            # Key facts + recommended actions
            sections.append({
                "type": "situation",
                "content": entity_summary or {},
            })
            sections.append({
                "type": "primary_assessment",
                "content": display_hyps[0] if display_hyps else {},
            })
            if rep.include_alternative_hypotheses and len(display_hyps) > 1:
                sections.append({
                    "type": "alternatives",
                    "content": display_hyps[1:],
                })
            if rep.include_uncertainty_notes:
                sections.append({
                    "type": "uncertainty",
                    "content": "See hypothesis uncertainty estimates",
                })
            if not rep.include_raw_scores:
                suppressed.append("raw_scores")
            if not rep.include_methodology:
                suppressed.append("methodology")

        elif rep.detail_level == ReportingDetail.ANALYST_DETAIL:
            # Full technical breakdown
            sections.append({"type": "situation", "content": entity_summary or {}})
            sections.append({"type": "all_hypotheses", "content": display_hyps})
            if raw_evidence:
                sections.append({"type": "raw_evidence", "content": raw_evidence})
            sections.append({"type": "methodology", "content": "Full scoring pipeline details available"})
            sections.append({"type": "uncertainty", "content": "Per-hypothesis uncertainty breakdown"})

        return FormattedReport(
            detail_level=rep.detail_level.value,
            classification=rep.classification_marking,
            sections=sections,
            suppressed_fields=suppressed,
            language=rep.language_preference,
        )

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def get_adjustment_log(self, last_n: int = 50) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._adjustment_log[-last_n:]]

    def clear_log(self) -> int:
        count = len(self._adjustment_log)
        self._adjustment_log.clear()
        return count
