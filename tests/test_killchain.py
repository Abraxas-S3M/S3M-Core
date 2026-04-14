"""Unit tests for autonomous kill-chain infrastructure.

Military context:
Tests verify safety gates, authority logic, and deterministic target-to-engage
pipeline behavior for safety-critical tactical operations.
"""

import math

from services.killchain import F2T2EAPipeline
from services.killchain.models import EngagementAuthority, EngagementRequest, KillChainPhase, TargetClassification
from services.killchain.safety_interlocks import KillChainSafetyInterlocks
from services.killchain.weapon_target_pairing import WeaponTargetPairing


def test_find_returns_target_classifications_from_object_detector():
    pipeline = F2T2EAPipeline()
    targets = pipeline.find({"image_path": "stub.jpg"})
    assert len(targets) >= 1
    assert targets[0].target_id.startswith("tgt-")


def test_targeting_creates_engagement_request_with_threat_assessment():
    pipeline = F2T2EAPipeline()
    t = TargetClassification(
        target_id="T1",
        classification="ENEMY_UAV",
        confidence=0.9,
        position=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        source="yolo",
        first_detected=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        last_updated=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        track_id="",
        is_military_objective=None,
        civilian_proximity_m=300.0,
        collateral_risk="LOW",
        image_evidence=None,
    )
    req = pipeline.target(t)
    assert isinstance(req, EngagementRequest)
    assert "is_valid_target" in req.threat_assessment


def test_targeting_uses_allocator_when_configured():
    class StubAllocation:
        effector_type = "sam_medium"
        reasoning = "Layered interceptor selected"

    class StubAllocationResult:
        allocated = True
        allocation = StubAllocation()
        reasoning = "Allocated to SAM layer"

    class StubAllocator:
        def __init__(self):
            self.calls = []

        def allocate(self, **kwargs):
            self.calls.append(kwargs)
            return StubAllocationResult()

    allocator = StubAllocator()
    pipeline = F2T2EAPipeline(target_allocator=allocator)
    t = TargetClassification(
        target_id="T-ALLOC",
        classification="ENEMY_UAV",
        confidence=0.95,
        position=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        source="yolo",
        first_detected=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        last_updated=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        track_id="",
        is_military_objective=None,
        civilian_proximity_m=300.0,
        collateral_risk="LOW",
        image_evidence=None,
    )
    req = pipeline.target(t)
    assert allocator.calls
    assert req.weapon_type == "sam_medium"
    assert "Allocated to SAM layer" in req.xai_explanation


def test_hitl_requires_human_approval():
    pipeline = F2T2EAPipeline(authority_level=EngagementAuthority.HITL)
    t = pipeline.find({"image_path": "stub.jpg"})[0]
    req = pipeline.target(t)
    assert req.human_approval_required is True
    assert math.isinf(req.human_approval_timeout_seconds)


def test_hotl_has_30_second_timeout():
    pipeline = F2T2EAPipeline(authority_level=EngagementAuthority.HOTL)
    t = pipeline.find({"image_path": "stub.jpg"})[0]
    req = pipeline.target(t)
    assert req.human_approval_required is True
    assert req.human_approval_timeout_seconds == 30.0


def test_safety_interlocks_block_engagement_when_target_civilian():
    interlocks = KillChainSafetyInterlocks()
    req = EngagementRequest(
        request_id="R1",
        target_id="T1",
        authority_level=EngagementAuthority.HITL,
        roe_level="weapons_tight",
        weapon_type="direct_fire",
        platform_id="P1",
        requesting_agent="test",
        phase=KillChainPhase.TARGET,
        confidence=0.9,
        threat_assessment='{"is_valid_target": false, "label": "CIVILIAN"}',
        collateral_estimate="LOW",
        roe_compliant=True,
        xai_explanation="ok",
        human_approval_required=True,
        human_approval_timeout_seconds=float("inf"),
        human_decision=None,
        human_decision_by=None,
        human_decision_at=None,
        status="approved",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    req.__dict__["audit_entries_count"] = 1
    allowed, reason = interlocks.validate_engagement(req)
    assert allowed is False
    assert "civilian" in reason.lower() or "military objective" in reason.lower()


def test_safety_interlocks_block_when_collateral_unacceptable():
    interlocks = KillChainSafetyInterlocks()
    req = EngagementRequest(
        request_id="R2",
        target_id="T2",
        authority_level=EngagementAuthority.HITL,
        roe_level="weapons_tight",
        weapon_type="direct_fire",
        platform_id="P1",
        requesting_agent="test",
        phase=KillChainPhase.TARGET,
        confidence=0.9,
        threat_assessment='{"is_valid_target": true}',
        collateral_estimate="UNACCEPTABLE",
        roe_compliant=True,
        xai_explanation="ok",
        human_approval_required=True,
        human_approval_timeout_seconds=float("inf"),
        human_decision=None,
        human_decision_by=None,
        human_decision_at=None,
        status="approved",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    req.__dict__["audit_entries_count"] = 1
    allowed, reason = interlocks.validate_engagement(req)
    assert allowed is False
    assert "collateral" in reason.lower()


def test_safety_interlocks_block_when_confidence_low():
    interlocks = KillChainSafetyInterlocks()
    req = EngagementRequest(
        request_id="R3",
        target_id="T3",
        authority_level=EngagementAuthority.HITL,
        roe_level="weapons_tight",
        weapon_type="direct_fire",
        platform_id="P1",
        requesting_agent="test",
        phase=KillChainPhase.TARGET,
        confidence=0.4,
        threat_assessment='{"is_valid_target": true}',
        collateral_estimate="LOW",
        roe_compliant=True,
        xai_explanation="ok",
        human_approval_required=True,
        human_approval_timeout_seconds=float("inf"),
        human_decision=None,
        human_decision_by=None,
        human_decision_at=None,
        status="approved",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    req.__dict__["audit_entries_count"] = 1
    allowed, reason = interlocks.validate_engagement(req)
    assert allowed is False
    assert "confidence" in reason.lower()


def test_full_chain_end_to_end_with_hitl_authority():
    pipeline = F2T2EAPipeline(authority_level=EngagementAuthority.HITL)
    output = pipeline.execute_chain({"image_path": "stub.jpg"})
    assert "find" in output
    assert output["target"] is not None


def test_weapon_target_pairing_returns_appropriate_weapon_for_enemy_uav():
    pairing = WeaponTargetPairing()
    target = TargetClassification(
        target_id="T1",
        classification="ENEMY_UAV",
        confidence=0.85,
        position=(0, 0, 0),
        velocity=(0, 0, 0),
        source="yolo",
        first_detected=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        last_updated=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        track_id="trk",
        is_military_objective=True,
        civilian_proximity_m=200,
        collateral_risk="LOW",
        image_evidence=None,
    )
    choice = pairing.pair(target, [{"type": "air_to_air_missile", "range_m": 3000, "collateral_radius_m": 20}])
    assert choice["weapon"]["type"] == "air_to_air_missile"
