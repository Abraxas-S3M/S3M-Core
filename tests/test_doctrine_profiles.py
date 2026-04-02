# File: tests/test_doctrine_profiles.py
"""Tests for Chunk 5: Sovereign AI Personality Layer / Doctrine Profiles.

Proves:
  1. Doctrine loads correctly from dict and built-ins
  2. Profile changes thresholds predictably
  3. Bias adjustments are logged with full audit trail
  4. Different reporting policies produce different detail levels
  5. Doctrine does not overwrite raw evidence
  6. Profile switching is audited
  7. Domain priority biasing works
  8. Corroboration requirements affect scores
  9. Escalation tolerance influences alerting
"""

import sys
sys.path.insert(0, ".")

from src.doctrine.doctrine_models import (
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
from src.doctrine.doctrine_profile_manager import DoctrineProfileManager
from src.doctrine.policy_bias_engine import PolicyBiasEngine, BiasResult


# =====================================================================
# Test 1: Doctrine loads correctly
# =====================================================================

def test_doctrine_loads_correctly():
    """Built-in profiles load and serialize without error."""
    mgr = DoctrineProfileManager()
    count = mgr.register_builtin_profiles()
    assert count == 3, f"Expected 3 built-ins, got {count}"
    assert mgr.count() == 3

    # Retrieve by name
    gulf = mgr.get("saudi_gulf_defensive")
    assert gulf is not None
    assert gulf.name == "saudi_gulf_defensive"
    assert gulf.engagement.escalation_tolerance == EscalationTolerance.CONSERVATIVE
    assert gulf.region.theater == "CENTCOM AOR"
    assert "Houthi" in gulf.region.priority_threat_actors
    assert gulf.intelligence_bias.min_corroboration_sources == 2
    assert gulf.reporting.language_preference == "bilingual"

    # Serialize round-trip
    d = gulf.to_dict()
    assert d["name"] == "saudi_gulf_defensive"
    assert "engagement" in d
    assert "intelligence_bias" in d
    assert "reporting" in d
    assert "confidence" in d
    assert "region" in d

    # Load from dict
    restored = DoctrineProfile.from_dict(d)
    assert restored.name == gulf.name
    assert restored.engagement.escalation_tolerance == gulf.engagement.escalation_tolerance
    assert restored.intelligence_bias.min_corroboration_sources == gulf.intelligence_bias.min_corroboration_sources

    # List all
    summaries = mgr.list_profiles()
    assert len(summaries) == 3
    names = {s["name"] for s in summaries}
    assert "saudi_gulf_defensive" in names
    assert "heightened_readiness" in names
    assert "executive_overview" in names

    print("PASS: Doctrine loads correctly from built-ins and dict")


# =====================================================================
# Test 2: Profile changes thresholds predictably
# =====================================================================

def test_profile_changes_thresholds():
    """Different profiles produce different effective thresholds."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()

    defensive = mgr.get("saudi_gulf_defensive")
    heightened = mgr.get("heightened_readiness")
    executive = mgr.get("executive_overview")

    assert defensive is not None and heightened is not None and executive is not None

    # Defensive: conservative_factor=1.15, alert_threshold=0.55
    # Heightened: conservative_factor=0.85, alert_threshold=0.35
    # Executive: conservative_factor=1.3, alert_threshold=0.7

    d_threshold = defensive.confidence.get_effective_threshold(0.5)
    h_threshold = heightened.confidence.get_effective_threshold(0.5)
    e_threshold = executive.confidence.get_effective_threshold(0.5)

    # Heightened should have lowest effective threshold (most permissive)
    assert h_threshold < d_threshold, \
        f"Heightened ({h_threshold}) should < defensive ({d_threshold})"
    # Executive should have highest (most conservative)
    assert e_threshold > d_threshold, \
        f"Executive ({e_threshold}) should > defensive ({d_threshold})"

    # Alert thresholds differ
    assert heightened.confidence.alert_confidence_threshold < defensive.confidence.alert_confidence_threshold
    assert executive.confidence.alert_confidence_threshold > defensive.confidence.alert_confidence_threshold

    print("PASS: Profile changes thresholds predictably")


# =====================================================================
# Test 3: Bias adjustments are logged
# =====================================================================

def test_bias_adjustments_logged():
    """Every doctrine-driven score adjustment produces an audit record."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()
    mgr.activate("saudi_gulf_defensive")
    profile = mgr.get_active()
    assert profile is not None

    engine = PolicyBiasEngine(profile)

    # Apply bias to a maritime signal (HIGH priority domain)
    result = engine.apply_confidence_bias(
        raw_score=0.6, domain="maritime", source_count=1,
    )

    # Maritime is HIGH priority → should be boosted
    assert result.was_adjusted, "Maritime should be adjusted (HIGH priority)"
    assert result.adjusted_value != result.raw_value
    assert len(result.adjustments) >= 1

    # Check audit trail
    log = engine.get_adjustment_log()
    assert len(log) >= 1
    for entry in log:
        assert entry["type"] != ""
        assert entry["rule"] != ""
        assert entry["explanation"] != ""

    # The result should have the doctrine profile name
    assert result.doctrine_profile_name == "saudi_gulf_defensive"

    # Serialization
    d = result.to_dict()
    assert d["was_adjusted"] == True
    assert d["doctrine_profile"] == "saudi_gulf_defensive"
    assert len(d["adjustments"]) >= 1

    print("PASS: Bias adjustments are logged with full audit trail")


# =====================================================================
# Test 4: Different reporting policies produce different detail
# =====================================================================

def test_reporting_detail_levels():
    """Executive, operator, and analyst reports have different structures."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()

    hypotheses = [
        {"label": "continue_course", "probability": 0.55, "uncertainty": {"spatial_radius_m": 10}},
        {"label": "turn_left", "probability": 0.25, "uncertainty": {"spatial_radius_m": 15}},
        {"label": "stop", "probability": 0.20, "uncertainty": {"spatial_radius_m": 5}},
    ]
    raw_evidence = {"radar_returns": 5, "classification": "hostile_uav"}
    entity_summary = {"entity_id": "ent-001", "type": "aircraft"}

    # Executive summary
    exec_profile = mgr.get("executive_overview")
    assert exec_profile is not None
    exec_engine = PolicyBiasEngine(exec_profile)
    exec_report = exec_engine.format_for_reporting(hypotheses, raw_evidence, entity_summary)

    assert exec_report.detail_level == "executive_summary"
    # Executive should suppress many fields
    assert "raw_scores" in exec_report.suppressed_fields
    assert "methodology" in exec_report.suppressed_fields
    assert "alternative_hypotheses" in exec_report.suppressed_fields
    # Should have minimal sections
    assert len(exec_report.sections) <= 2

    # Analyst detail
    analyst_profile = mgr.get("heightened_readiness")
    assert analyst_profile is not None
    analyst_engine = PolicyBiasEngine(analyst_profile)
    analyst_report = analyst_engine.format_for_reporting(hypotheses, raw_evidence, entity_summary)

    assert analyst_report.detail_level == "analyst_detail"
    assert analyst_report.classification == "SECRET"
    # Analyst should have raw evidence section
    section_types = [s["type"] for s in analyst_report.sections]
    assert "raw_evidence" in section_types, f"Analyst report should include raw_evidence, got {section_types}"
    assert "methodology" in section_types
    # Should have more sections than executive
    assert len(analyst_report.sections) > len(exec_report.sections)

    # Operator brief
    op_profile = mgr.get("saudi_gulf_defensive")
    assert op_profile is not None
    op_engine = PolicyBiasEngine(op_profile)
    op_report = op_engine.format_for_reporting(hypotheses, raw_evidence, entity_summary)

    assert op_report.detail_level == "operator_brief"
    # Should be between executive and analyst in detail
    assert len(op_report.sections) >= len(exec_report.sections)

    print("PASS: Different reporting policies produce different detail levels")


# =====================================================================
# Test 5: Doctrine does not overwrite raw evidence
# =====================================================================

def test_doctrine_preserves_raw_evidence():
    """Bias adjustments preserve the original raw score in every result."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()
    mgr.activate("heightened_readiness")
    profile = mgr.get_active()
    assert profile is not None

    engine = PolicyBiasEngine(profile)

    raw = 0.45
    result = engine.apply_confidence_bias(raw_score=raw, domain="cyber", source_count=1)

    # Raw value MUST be preserved
    assert result.raw_value == raw, \
        f"Raw value must be preserved: expected {raw}, got {result.raw_value}"

    # Adjusted may differ but raw is untouched
    assert result.raw_value == 0.45

    # Every adjustment in the log records the raw value before change
    for adj in result.adjustments:
        assert adj.raw_value != 0 or adj.adjusted_value != 0, \
            "Each adjustment must record the value transformation"

    # Even with extreme doctrine, raw evidence is kept
    extreme_profile = DoctrineProfile(
        name="extreme",
        intelligence_bias=IntelligenceBiasPolicy(
            domain_priorities={"test": DomainPriority.SUPPRESSED},
            min_corroboration_sources=5,
        ),
        confidence=ConfidenceAdjustmentPolicy(conservative_factor=2.0),
    )
    extreme_engine = PolicyBiasEngine(extreme_profile)
    extreme_result = extreme_engine.apply_confidence_bias(
        raw_score=0.8, domain="test", source_count=1, is_critical=True,
    )

    assert extreme_result.raw_value == 0.8, "Raw must be preserved even under extreme doctrine"
    assert extreme_result.adjusted_value < 0.8, "Extreme doctrine should reduce adjusted score"
    assert extreme_result.adjusted_value > 0.0, "Score should not be zeroed out"

    print("PASS: Doctrine never overwrites raw evidence")


# =====================================================================
# Test 6: Profile switching is audited
# =====================================================================

def test_profile_switching_audit():
    """Every profile activation switch is recorded in the audit log."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()

    mgr.activate("saudi_gulf_defensive", actor="operator-1", reason="Normal ops")
    assert mgr.get_active().name == "saudi_gulf_defensive"

    mgr.activate("heightened_readiness", actor="commander", reason="Intel indicates threat")
    assert mgr.get_active().name == "heightened_readiness"

    mgr.activate("executive_overview", actor="general", reason="Briefing prep")
    assert mgr.get_active().name == "executive_overview"

    log = mgr.get_audit_log()
    # Should have registration entries + activation entries
    activations = [e for e in log if e["action"] == "activated"]
    assert len(activations) == 3

    # The last activation should record the previous profile
    latest = activations[-1]
    assert latest["profile_name"] == "executive_overview"
    assert latest["previous_profile_name"] == "heightened_readiness"
    assert latest["actor"] == "general"
    assert latest["reason"] == "Briefing prep"

    print("PASS: Profile switching is audited")


# =====================================================================
# Test 7: Domain priority biasing
# =====================================================================

def test_domain_priority_biasing():
    """HIGH priority domains get boosted, SUPPRESSED get penalised."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()
    mgr.activate("saudi_gulf_defensive")
    profile = mgr.get_active()
    engine = PolicyBiasEngine(profile)

    # Maritime = HIGH priority
    maritime_result = engine.apply_confidence_bias(raw_score=0.5, domain="maritime")
    # OSINT = LOW priority
    osint_result = engine.apply_confidence_bias(raw_score=0.5, domain="osint")

    assert maritime_result.adjusted_value > osint_result.adjusted_value, \
        f"Maritime ({maritime_result.adjusted_value}) should > OSINT ({osint_result.adjusted_value})"

    # Verify the priority multipliers are correct
    bias = profile.intelligence_bias
    assert bias.get_priority_multiplier("maritime") > bias.get_priority_multiplier("osint")
    assert bias.get_priority_multiplier("maritime") == 1.25  # HIGH
    assert bias.get_priority_multiplier("osint") == 0.75     # LOW

    print("PASS: Domain priority biasing works correctly")


# =====================================================================
# Test 8: Corroboration requirements
# =====================================================================

def test_corroboration_requirements():
    """Fewer sources than required reduces confidence."""
    profile = DoctrineProfile(
        name="strict_corroboration",
        intelligence_bias=IntelligenceBiasPolicy(
            min_corroboration_sources=3,
            require_multi_domain_for_critical=True,
        ),
    )
    engine = PolicyBiasEngine(profile)

    # 3 sources (meets requirement)
    met = engine.apply_confidence_bias(raw_score=0.7, source_count=3)
    # 1 source (below requirement)
    unmet = engine.apply_confidence_bias(raw_score=0.7, source_count=1)

    assert met.adjusted_value > unmet.adjusted_value, \
        f"3 sources ({met.adjusted_value}) should > 1 source ({unmet.adjusted_value})"

    # Check the corroboration penalty is logged
    corr_adjs = [a for a in unmet.adjustments if a.adjustment_type == "corroboration_penalty"]
    assert len(corr_adjs) >= 1, "Corroboration penalty should be logged"
    assert "source" in corr_adjs[0].explanation.lower()

    # Critical with single source gets additional penalty
    critical_single = engine.apply_confidence_bias(
        raw_score=0.7, source_count=1, is_critical=True,
    )
    assert critical_single.adjusted_value < unmet.adjusted_value, \
        f"Critical single-source ({critical_single.adjusted_value}) should < non-critical ({unmet.adjusted_value})"

    print("PASS: Corroboration requirements affect scores")


# =====================================================================
# Test 9: Escalation tolerance
# =====================================================================

def test_escalation_tolerance():
    """Doctrine controls when alerts and escalations are triggered."""
    mgr = DoctrineProfileManager()
    mgr.register_builtin_profiles()

    # Heightened readiness: alert_threshold=0.35, escalation_threshold=0.55
    mgr.activate("heightened_readiness")
    heightened_engine = PolicyBiasEngine(mgr.get_active())

    # Executive overview: alert_threshold=0.7
    exec_profile = mgr.get("executive_overview")
    exec_engine = PolicyBiasEngine(exec_profile)

    # A score of 0.5 should alert under heightened but not executive
    assert heightened_engine.should_alert(0.5) == True, \
        "0.5 should alert under heightened (threshold=0.35)"
    assert exec_engine.should_alert(0.5) == False, \
        "0.5 should NOT alert under executive (threshold=0.7)"

    # Escalation: heightened auto-escalates "high" threat level
    assert heightened_engine.should_escalate(0.3, threat_level="high") == True
    # Executive doesn't auto-escalate "high"
    assert exec_engine.should_escalate(0.3, threat_level="high") == False

    print("PASS: Escalation tolerance influences alerting correctly")


# =====================================================================
# Run all tests
# =====================================================================

if __name__ == "__main__":
    test_doctrine_loads_correctly()
    test_profile_changes_thresholds()
    test_bias_adjustments_logged()
    test_reporting_detail_levels()
    test_doctrine_preserves_raw_evidence()
    test_profile_switching_audit()
    test_domain_priority_biasing()
    test_corroboration_requirements()
    test_escalation_tolerance()
    print("\nAll Doctrine Profile tests passed")
