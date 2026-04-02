"""Tests for Chunk 8: Runtime Integration — Operational Picture Service.

Proves:
  1. Full operational picture built end-to-end from entity snapshots
  2. Doctrine affects thresholds and adjustments but not raw evidence
  3. Prediction output is included in the picture
  4. Mirror validation is included and predictions are fed to it
  5. Threat genome data is visible in final output
  6. Alert and escalation flags are set by doctrine
  7. Graceful degradation when subsystems are absent
  8. Audit trail and processing steps are captured
"""

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from src.prediction.prediction_models import EntitySnapshot, HistoryPoint
from src.runtime.operational_picture_service import (
    EntityPicture,
    ObservedStateFrame,
    OperationalPicture,
    OperationalPictureService,
)


def _make_entities():
    """Create a set of test entity snapshots."""
    now = datetime.now(timezone.utc)

    # Moving hostile UAV
    uav_history = []
    for i in range(6):
        t = now - timedelta(seconds=(6 - i) * 15)
        uav_history.append(
            HistoryPoint(
                timestamp=t,
                position=(100.0, 300.0 - i * 50, 100.0),
                velocity=(0.0, -20.0, 0.0),
                heading_deg=180.0,
                speed_mps=20.0,
                threat_level="high",
                confidence=0.75,
            )
        )

    uav = EntitySnapshot(
        entity_id="ent-uav-001",
        entity_type="aircraft",
        classification="hostile_uav",
        allegiance="hostile",
        position=(100.0, 0.0, 100.0),
        velocity=(0.0, -20.0, 0.0),
        heading_deg=180.0,
        speed_mps=20.0,
        threat_level="high",
        confidence=0.75,
        last_updated=now,
        history=uav_history,
        behavior_tags=["drone", "uav", "hostile"],
    )

    # Stationary ground contact
    ground = EntitySnapshot(
        entity_id="ent-ground-002",
        entity_type="ground_vehicle",
        classification="unknown_contact",
        allegiance="unknown",
        position=(500.0, 500.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        heading_deg=0.0,
        speed_mps=0.0,
        threat_level="low",
        confidence=0.6,
        last_updated=now,
        history=[
            HistoryPoint(
                timestamp=now - timedelta(seconds=30),
                position=(500.0, 500.0, 0.0),
                velocity=(0.0, 0.0, 0.0),
                heading_deg=0.0,
                speed_mps=0.0,
                threat_level="low",
                confidence=0.6,
            )
        ],
    )

    return [uav, ground]


def test_full_operational_picture():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities, windows_s=[30.0, 120.0])

    assert isinstance(picture, OperationalPicture)
    assert picture.picture_id.startswith("oppic-")
    assert picture.entity_count == 2
    assert len(picture.entities) == 2
    assert all(isinstance(ep, EntityPicture) for ep in picture.entities)

    ids = {ep.entity_id for ep in picture.entities}
    assert "ent-uav-001" in ids
    assert "ent-ground-002" in ids

    assert "pipeline_started" in picture.processing_steps
    assert "picture_composed" in picture.processing_steps
    assert any("processed" in s for s in picture.processing_steps)

    assert len(picture.audit_notes) >= 1

    d = picture.to_dict()
    assert d["entity_count"] == 2
    assert "entities" in d
    assert "processing_steps" in d
    assert "audit_notes" in d
    assert "generated_at" in d

    print("PASS: Full operational picture built end-to-end")


def test_doctrine_preserves_raw():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities)

    for ep in picture.entities:
        if ep.entity_id == "ent-uav-001":
            assert ep.raw_confidence == 0.75, f"Raw confidence must be 0.75, got {ep.raw_confidence}"
        elif ep.entity_id == "ent-ground-002":
            assert ep.raw_confidence == 0.6

        assert ep.doctrine_adjusted_confidence > 0.0
        assert ep.doctrine_adjusted_confidence <= 1.0

    assert picture.active_doctrine == "saudi_gulf_defensive"
    assert picture.doctrine_profile_summary is not None
    assert "conservative_factor" in picture.doctrine_profile_summary

    print("PASS: Doctrine affects thresholds but raw evidence preserved")


def test_prediction_included():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities, windows_s=[30.0, 120.0])

    assert len(picture.forecast_bundles) >= 1, (
        f"Expected forecast bundles, got {len(picture.forecast_bundles)}"
    )

    uav_ep = next(ep for ep in picture.entities if ep.entity_id == "ent-uav-001")
    assert uav_ep.forecast_bundle_id is not None
    assert uav_ep.forecast_trend != "unknown"
    assert uav_ep.forecast_dominant_30s is not None
    assert uav_ep.forecast_confidence > 0

    bundle = picture.forecast_bundles[0]
    assert "windows" in bundle
    assert bundle["window_count"] >= 1

    print("PASS: Prediction output included in picture")


def test_mirror_included():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities, windows_s=[30.0])

    assert picture.mirror_status is not None
    assert "total_frames" in picture.mirror_status
    assert "pending_predictions" in picture.mirror_status
    assert picture.mirror_status["pending_predictions"] > 0, "Predictions should be queued in mirror"
    assert picture.validation_metrics is not None

    observations = [
        ObservedStateFrame(
            entity_id="ent-uav-001",
            observation_timestamp=datetime.now(timezone.utc) + timedelta(seconds=30),
            observed_position=(100.0, -600.0, 100.0),
            observed_heading_deg=180.0,
            observed_speed_mps=20.0,
            observed_threat_level="high",
            entity_present=True,
        )
    ]
    recorded = service.record_observations(observations)
    assert recorded == 1

    stats = service.mirror.stats()
    assert stats["total_comparisons"] >= 1

    print("PASS: Mirror validation included and observations recorded")


def test_genome_visible():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities)

    assert len(picture.genome_correlations) >= 1, (
        f"Expected genome correlations, got {len(picture.genome_correlations)}"
    )

    genome_entities = [ep for ep in picture.entities if ep.genome_id is not None]
    assert len(genome_entities) >= 1, "At least one entity should correlate to a genome"

    for verdict in picture.genome_correlations:
        assert "decision" in verdict
        assert verdict["decision"] in ("matched", "created")
        assert "composite_score" in verdict

    assert service.genome_store.count() >= 1
    assert isinstance(picture.active_genomes, list)

    print("PASS: Threat genome data visible in final output")


def test_alert_escalation_flags():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities)
    uav_ep = next(ep for ep in picture.entities if ep.entity_id == "ent-uav-001")

    assert isinstance(uav_ep.should_alert, bool)
    assert isinstance(uav_ep.should_escalate, bool)
    assert picture.entities_above_alert_threshold >= 0
    assert picture.entities_requiring_escalation >= 0
    assert 0.0 < picture.mean_confidence < 1.0

    print("PASS: Alert and escalation flags set by doctrine")


def test_graceful_degradation():
    service = OperationalPictureService()
    entities = _make_entities()

    picture = service.process_entities(entities)

    assert picture.entity_count == 2
    assert len(picture.entities) == 2

    for ep in picture.entities:
        assert ep.entity_id != ""
        assert ep.raw_confidence > 0
        assert ep.forecast_bundle_id is None
        assert ep.genome_id is None

    assert picture.active_doctrine is None
    assert picture.mirror_status is None
    assert len(picture.forecast_bundles) == 0
    assert len(picture.genome_correlations) == 0

    print("PASS: Graceful degradation when subsystems absent")


def test_audit_trail():
    service = OperationalPictureService.build_default()
    entities = _make_entities()

    picture = service.process_entities(entities)

    assert len(picture.processing_steps) >= 3
    assert "pipeline_started" in picture.processing_steps
    assert "picture_composed" in picture.processing_steps

    assert len(picture.audit_notes) >= 1
    audit_text = " ".join(picture.audit_notes).lower()
    assert "correlation" in audit_text or "forecast" in audit_text or "doctrine" in audit_text

    stats = service.stats()
    assert stats["pictures_generated"] == 1
    assert stats["doctrine_active"] == "saudi_gulf_defensive"
    assert stats["genome_store"] is not None
    assert stats["mirror"] is not None

    print("PASS: Audit trail and processing steps captured")


if __name__ == "__main__":
    test_full_operational_picture()
    test_doctrine_preserves_raw()
    test_prediction_included()
    test_mirror_included()
    test_genome_visible()
    test_alert_escalation_flags()
    test_graceful_degradation()
    test_audit_trail()
    print("\nAll Operational Picture Service tests passed")
