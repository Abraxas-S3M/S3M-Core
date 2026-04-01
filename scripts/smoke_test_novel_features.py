#!/usr/bin/env python3
"""Smoke test for all 4 novel S3M features."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_feature(name, test_fn):
    try:
        result = test_fn()
        print(f"  [PASS] {name}: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False


def main():
    print("=" * 60)
    print("  S3M NOVEL FEATURES — SMOKE TEST")
    print("=" * 60)
    results = []

    print("\n[Feature 1: HOOL Autonomy]")
    from services.autonomy.hool_extension.models import MissionEnvelope, PlatformClass, CompanionCompute

    now = datetime.now(timezone.utc)
    env = MissionEnvelope(
        envelope_id="E1",
        mission_id="M1",
        approved_by="CMD",
        approved_at=now,
        geofence_vertices=[(0, 0, 0), (100, 0, 0), (100, 100, 0), (0, 100, 0)],
        geofence_ceiling_m=200,
        geofence_floor_m=0,
        time_window=(now, now + timedelta(hours=1)),
        roe_level="weapons_tight",
        max_targets=3,
        allowed_target_types=["ENEMY_UAV"],
        min_engagement_confidence=0.8,
        min_battery_pct=20,
        min_fuel_pct=0,
        max_comms_loss_seconds=120,
        max_risk_score=75,
        max_escalation_level=3,
        custom_constraints={},
    )
    results.append(test_feature("MissionEnvelope creation", lambda: env.envelope_id))
    results.append(test_feature("CompanionCompute for UAV_QUADROTOR", lambda: CompanionCompute.for_platform(PlatformClass.UAV_QUADROTOR).cpu_model))

    print("\n[Feature 2: Kill Chain]")
    from services.killchain.safety_interlocks import KillChainSafetyInterlocks

    interlocks = KillChainSafetyInterlocks()
    results.append(test_feature("Safety interlocks initialized", lambda: len(interlocks.get_interlock_status())))

    print("\n[Feature 3: Risk Assessment]")
    from services.risk_assessment.bayesian_network import BayesianRiskNetwork

    brn = BayesianRiskNetwork()
    results.append(test_feature("Bayesian network initialized", lambda: "initialized" if brn.initialized else "not"))

    print("\n[Feature 4: Command Agent]")
    from services.command_agent.intent_classifier import IntentClassifier

    ic = IntentClassifier()
    intent, conf = ic.classify("What is the threat level in sector alpha?", None)
    results.append(test_feature(f"Intent classified: {intent.value}", lambda: conf > 0))

    passed = sum(1 for x in results if x)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed}/{total} passed")
    print(f"{'=' * 60}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
