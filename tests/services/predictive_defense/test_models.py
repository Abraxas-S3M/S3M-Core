"""Unit tests for predictive defense data models.

Military context:
These tests validate serialized prediction outputs consumed by downstream
engagement planners that pre-position interceptors ahead of swarm arrival.
"""

from __future__ import annotations

from services.predictive_defense.models import (
    DefensePosture,
    PrePositionCommand,
    PredictiveAlert,
    SwarmIntent,
    SwarmPrediction,
    ThreatTrajectoryPrediction,
)


def test_threat_trajectory_prediction_to_dict_rounds_and_serializes() -> None:
    prediction = ThreatTrajectoryPrediction(
        track_id="trk-100",
        target_classification="UAV",
        genome_match="houthi_drone_v2",
        genome_confidence=0.81234,
        current_position=(10.0, 20.0, 30.0),
        current_speed_mps=55.67,
        current_heading_deg=181.234,
        predicted_30s=(100.0, 200.0, 300.0),
        predicted_60s=(150.0, 250.0, 350.0),
        range_to_asset_now_m=2044.8,
        time_to_zone_entry_s=58.91,
        time_to_asset_s=84.44,
        prediction_confidence=0.93456,
        genome_bias_applied=True,
        behavioral_pattern="approach",
    )

    payload = prediction.to_dict()

    assert payload["track_id"] == "trk-100"
    assert payload["classification"] == "UAV"
    assert payload["genome_confidence"] == 0.812
    assert payload["current_position"] == [10.0, 20.0, 30.0]
    assert payload["current_speed_mps"] == 55.7
    assert payload["current_heading_deg"] == 181.2
    assert payload["predicted_30s"] == [100.0, 200.0, 300.0]
    assert payload["predicted_120s"] is None
    assert payload["range_to_asset_now_m"] == 2045.0
    assert payload["time_to_zone_entry_s"] == 58.9
    assert payload["time_to_asset_s"] == 84.4
    assert payload["confidence"] == 0.935
    assert payload["genome_bias"] is True
    assert payload["behavioral_pattern"] == "approach"


def test_swarm_prediction_to_dict_serializes_intent_and_geometry() -> None:
    swarm = SwarmPrediction(
        track_ids=["trk-1", "trk-2", "trk-3"],
        track_count=3,
        intent=SwarmIntent.SATURATION,
        convergence_point=(3500.0, 4100.0, 250.0),
        convergence_time_s=92.66,
        approach_bearing_deg=47.88,
        average_speed_mps=42.44,
        first_arrival_s=71.22,
        last_arrival_s=102.88,
        effectors_required=4,
        estimated_pk_defense=0.61111,
        genome_match="swarm_genome_a",
    )

    payload = swarm.to_dict()

    assert payload["track_count"] == 3
    assert payload["intent"] == "saturation"
    assert payload["convergence_point"] == [3500.0, 4100.0, 250.0]
    assert payload["convergence_time_s"] == 92.7
    assert payload["approach_bearing_deg"] == 47.9
    assert payload["average_speed_mps"] == 42.4
    assert payload["first_arrival_s"] == 71.2
    assert payload["last_arrival_s"] == 102.9
    assert payload["effectors_required"] == 4
    assert payload["estimated_pk_defense"] == 0.611
    assert payload["genome_match"] == "swarm_genome_a"


def test_pre_position_command_to_dict_serializes_command_fields() -> None:
    command = PrePositionCommand(
        interceptor_id="int-7",
        target_track_id="trk-55",
        launch_now=True,
        intercept_position=(200.0, 500.0, 1200.0),
        launch_time_offset_s=2.25,
        time_to_station_s=24.44,
        engagement_window_s=31.06,
        reasoning="Predicted inbound path intersects sector bravo.",
        confidence=0.85444,
    )

    payload = command.to_dict()

    assert payload["interceptor_id"] == "int-7"
    assert payload["target_track_id"] == "trk-55"
    assert payload["launch_now"] is True
    assert payload["intercept_position"] == [200.0, 500.0, 1200.0]
    assert payload["launch_offset_s"] == 2.2
    assert payload["time_to_station_s"] == 24.4
    assert payload["engagement_window_s"] == 31.1
    assert payload["reasoning"] == "Predicted inbound path intersects sector bravo."
    assert payload["confidence"] == 0.854


def test_predictive_alert_to_dict_embeds_pre_position_commands() -> None:
    command = PrePositionCommand(interceptor_id="int-3", target_track_id="trk-9")
    alert = PredictiveAlert(
        severity="high",
        posture=DefensePosture.PRE_POSITION,
        title_en="Pre-position interceptors",
        title_ar="تموضع الاعتراضات",
        threat_count=2,
        time_to_impact_s=43.84,
        recommended_actions=["Launch ready interceptors", "Prioritize sector alpha"],
        pre_position_commands=[command],
    )

    payload = alert.to_dict()

    assert payload["severity"] == "high"
    assert payload["posture"] == "pre_position"
    assert payload["title_en"] == "Pre-position interceptors"
    assert payload["title_ar"] == "تموضع الاعتراضات"
    assert payload["threat_count"] == 2
    assert payload["time_to_impact_s"] == 43.8
    assert payload["recommended_actions"] == ["Launch ready interceptors", "Prioritize sector alpha"]
    assert len(payload["pre_position_commands"]) == 1
    assert payload["pre_position_commands"][0]["interceptor_id"] == "int-3"


def test_generated_identifiers_use_expected_prefixes() -> None:
    prediction = ThreatTrajectoryPrediction()
    swarm = SwarmPrediction()
    command = PrePositionCommand()
    alert = PredictiveAlert()

    assert prediction.prediction_id.startswith("ttp-")
    assert swarm.swarm_id.startswith("swarm-")
    assert command.command_id.startswith("ppc-")
    assert alert.alert_id.startswith("pa-")
