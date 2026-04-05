"""Pre-built closed-range validation scenarios for HOOL rehearsal.

Military/tactical context:
Each scenario emulates a compact mission segment to validate detection,
handoff, engagement, and convoy coordination under deterministic replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping
import json
import math

from src.autonomy.engagement_logic import EngagementPipeline
from src.platforms.common import ThreatPriority, Track
from src.platforms.fixed.horizon_adapter import HorizonAdapter, TrackStore
from src.platforms.payloads.weapon_adapters import RCWS127Adapter
from src.platforms.uav.warwar_adapter import WarWarAdapter
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.platforms.usv.g24_adapter import G24Adapter
from src.simulation.models import EntityType, SimEntity
from src.validation.aar_recorder import AARRecorder
from src.validation.fault_injector import FaultInjector, FaultScheduleEntry
from src.validation.replay_harness import TelemetryReplayHarness


@dataclass(frozen=True)
class DetectionEvent:
    """Synthetic sensor detection injected during scenario replay."""

    sim_time_s: float
    source_platform: str
    track_id: str
    position: tuple[float, float, float]
    confidence: float
    classification: str
    threat_priority: ThreatPriority = ThreatPriority.MEDIUM
    handoff_to: str | None = None
    ground_truth_position: tuple[float, float, float] | None = None


@dataclass
class ValidationScenario:
    """Scenario definition for reusable closed-range validation tests."""

    scenario_id: str
    name: str
    description: str
    platform_layout: dict[str, str]
    telemetry_sequences: dict[str, list[dict[str, Any]]]
    detection_events: list[DetectionEvent]
    objective_positions: dict[str, tuple[float, float, float]]
    objective_count: int
    expected_outcomes: dict[str, Any]
    fault_schedule: list[FaultScheduleEntry] = field(default_factory=list)
    objective_tolerance_m: float = 25.0


@dataclass
class ScenarioOutcome:
    """Outcome package returned after running one validation scenario."""

    scenario_id: str
    scenario_name: str
    success: bool
    metrics: dict[str, Any]
    counters: dict[str, int]
    validation_errors: list[str]
    replay_summary: dict[str, Any]
    markdown_aar: str


def _linear_platform_sequence(
    *,
    platform_id: str,
    platform_type: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    steps: int,
    dt_s: float = 1.0,
) -> list[dict[str, Any]]:
    seq: list[dict[str, Any]] = []
    total = max(1, steps - 1)
    for idx in range(steps):
        ratio = idx / float(total)
        position = (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
            start[2] + (end[2] - start[2]) * ratio,
        )
        seq.append(
            {
                "platform_id": platform_id,
                "platform_type": platform_type,
                "sim_time_s": round(idx * dt_s, 3),
                "position": [round(position[0], 3), round(position[1], 3), round(position[2], 3)],
                "health_state": "nominal",
                "autonomy_mode": "supervised",
                "metadata": {"military_context": "closed_range_validation"},
            }
        )
    return seq


def _build_prebuilt_scenarios() -> dict[str, ValidationScenario]:
    s1 = ValidationScenario(
        scenario_id="scenario_1_hmmwv_patrol",
        name="Scenario 1: HMMWV patrol with simulated radar detections",
        description="Ground patrol with fixed-site radar detections and engagement recommendations.",
        platform_layout={
            "hmmwv-patrol-1": "hmmwv",
            "horizon-radar-1": "horizon",
        },
        telemetry_sequences={
            "hmmwv-patrol-1": _linear_platform_sequence(
                platform_id="hmmwv-patrol-1",
                platform_type="ugv",
                start=(0.0, 0.0, 0.0),
                end=(300.0, 0.0, 0.0),
                steps=7,
            ),
            "horizon-radar-1": _linear_platform_sequence(
                platform_id="horizon-radar-1",
                platform_type="fixed",
                start=(0.0, 0.0, 0.0),
                end=(0.0, 0.0, 0.0),
                steps=7,
            ),
        },
        detection_events=[
            DetectionEvent(1.0, "horizon-radar-1", "radar-1", (220.0, 35.0, 0.0), 0.9, "hostile_vehicle", ThreatPriority.HIGH, None, (223.0, 35.0, 0.0)),
            DetectionEvent(3.0, "horizon-radar-1", "radar-2", (255.0, -12.0, 0.0), 0.88, "hostile_vehicle", ThreatPriority.HIGH, None, (258.0, -10.0, 0.0)),
            DetectionEvent(5.0, "horizon-radar-1", "radar-3", (288.0, 22.0, 0.0), 0.91, "hostile_vehicle", ThreatPriority.CRITICAL, None, (288.0, 20.0, 0.0)),
        ],
        objective_positions={"hmmwv-patrol-1": (300.0, 0.0, 0.0)},
        objective_count=1,
        expected_outcomes={
            "detections_min": 3,
            "engagements_min": 1,
            "mission_completion_min": 100.0,
        },
    )

    s2 = ValidationScenario(
        scenario_id="scenario_2_warwar_isr_handoff",
        name="Scenario 2: WarWar ISR with track handoff to Horizon",
        description="UAV ISR contact detection with handoff into Horizon track store.",
        platform_layout={
            "warwar-isr-1": "warwar",
            "horizon-node-2": "horizon",
        },
        telemetry_sequences={
            "warwar-isr-1": _linear_platform_sequence(
                platform_id="warwar-isr-1",
                platform_type="uav",
                start=(0.0, 0.0, 50.0),
                end=(420.0, 70.0, 70.0),
                steps=7,
            ),
            "horizon-node-2": _linear_platform_sequence(
                platform_id="horizon-node-2",
                platform_type="fixed",
                start=(10.0, 0.0, 0.0),
                end=(10.0, 0.0, 0.0),
                steps=7,
            ),
        },
        detection_events=[
            DetectionEvent(2.0, "warwar-isr-1", "isr-1", (320.0, 50.0, 0.0), 0.84, "hostile_uav", ThreatPriority.HIGH, "horizon-node-2", (325.0, 49.0, 0.0)),
            DetectionEvent(4.0, "warwar-isr-1", "isr-2", (360.0, 60.0, 0.0), 0.87, "hostile_uav", ThreatPriority.HIGH, "horizon-node-2", (364.0, 61.0, 0.0)),
        ],
        objective_positions={"warwar-isr-1": (420.0, 70.0, 70.0)},
        objective_count=1,
        expected_outcomes={
            "handoffs_min": 1,
            "recommendations_min": 1,
            "mission_completion_min": 100.0,
        },
    )

    s3 = ValidationScenario(
        scenario_id="scenario_3_g24_maritime_patrol",
        name="Scenario 3: G24 maritime patrol with AIS contacts",
        description="Maritime patrol with AIS contacts and safety-aware contact handling.",
        platform_layout={
            "g24-maritime-1": "g24",
            "horizon-maritime-1": "horizon",
        },
        telemetry_sequences={
            "g24-maritime-1": _linear_platform_sequence(
                platform_id="g24-maritime-1",
                platform_type="usv",
                start=(0.0, 0.0, 0.0),
                end=(520.0, 0.0, 0.0),
                steps=7,
            ),
            "horizon-maritime-1": _linear_platform_sequence(
                platform_id="horizon-maritime-1",
                platform_type="fixed",
                start=(20.0, 0.0, 0.0),
                end=(20.0, 0.0, 0.0),
                steps=7,
            ),
        },
        detection_events=[
            DetectionEvent(1.0, "horizon-maritime-1", "ais-1", (140.0, 30.0, 0.0), 0.8, "AIS_CONTACT", ThreatPriority.MEDIUM, None, (141.0, 31.0, 0.0)),
            DetectionEvent(2.0, "horizon-maritime-1", "ais-2", (260.0, -24.0, 0.0), 0.82, "AIS_CONTACT", ThreatPriority.MEDIUM, None, (260.0, -22.0, 0.0)),
            DetectionEvent(4.0, "horizon-maritime-1", "ais-3", (410.0, 10.0, 0.0), 0.84, "AIS_CONTACT", ThreatPriority.MEDIUM, None, (412.0, 9.0, 0.0)),
        ],
        objective_positions={"g24-maritime-1": (520.0, 0.0, 0.0)},
        objective_count=1,
        expected_outcomes={
            "ais_contacts_min": 2,
            "mission_completion_min": 100.0,
        },
    )

    s4 = ValidationScenario(
        scenario_id="scenario_4_hmmwv_convoy_overwatch",
        name="Scenario 4: HMMWV convoy (3 vehicles) with WarWar overwatch",
        description="Three-vehicle convoy with UAV overwatch and coordinated objective completion.",
        platform_layout={
            "convoy-1": "hmmwv",
            "convoy-2": "hmmwv",
            "convoy-3": "hmmwv",
            "warwar-overwatch": "warwar",
        },
        telemetry_sequences={
            "convoy-1": _linear_platform_sequence(
                platform_id="convoy-1",
                platform_type="ugv",
                start=(0.0, -20.0, 0.0),
                end=(460.0, -20.0, 0.0),
                steps=8,
            ),
            "convoy-2": _linear_platform_sequence(
                platform_id="convoy-2",
                platform_type="ugv",
                start=(0.0, 0.0, 0.0),
                end=(460.0, 0.0, 0.0),
                steps=8,
            ),
            "convoy-3": _linear_platform_sequence(
                platform_id="convoy-3",
                platform_type="ugv",
                start=(0.0, 20.0, 0.0),
                end=(460.0, 20.0, 0.0),
                steps=8,
            ),
            "warwar-overwatch": _linear_platform_sequence(
                platform_id="warwar-overwatch",
                platform_type="uav",
                start=(0.0, 0.0, 60.0),
                end=(460.0, 0.0, 80.0),
                steps=8,
            ),
        },
        detection_events=[
            DetectionEvent(3.0, "warwar-overwatch", "convoy-threat-1", (300.0, 60.0, 0.0), 0.86, "hostile_vehicle", ThreatPriority.HIGH, None, (302.0, 58.0, 0.0)),
        ],
        objective_positions={
            "convoy-1": (460.0, -20.0, 0.0),
            "convoy-2": (460.0, 0.0, 0.0),
            "convoy-3": (460.0, 20.0, 0.0),
        },
        objective_count=3,
        expected_outcomes={
            "convoy_arrived": True,
            "mission_completion_min": 100.0,
        },
    )

    s5 = ValidationScenario(
        scenario_id="scenario_5_full_hool_chain",
        name="Scenario 5: Full HOOL chain - Horizon detect -> RCWS track -> engage",
        description="End-to-end detect-track-engage chain under deterministic replay.",
        platform_layout={
            "horizon-killchain": "horizon",
            "rcws-carrier": "hmmwv",
        },
        telemetry_sequences={
            "horizon-killchain": _linear_platform_sequence(
                platform_id="horizon-killchain",
                platform_type="fixed",
                start=(0.0, 0.0, 0.0),
                end=(0.0, 0.0, 0.0),
                steps=6,
            ),
            "rcws-carrier": _linear_platform_sequence(
                platform_id="rcws-carrier",
                platform_type="ugv",
                start=(0.0, 0.0, 0.0),
                end=(120.0, 0.0, 0.0),
                steps=6,
            ),
        },
        detection_events=[
            DetectionEvent(2.0, "horizon-killchain", "killchain-1", (90.0, 15.0, 0.0), 0.95, "hostile_vehicle", ThreatPriority.CRITICAL, None, (92.0, 14.0, 0.0)),
        ],
        objective_positions={"rcws-carrier": (120.0, 0.0, 0.0)},
        objective_count=1,
        expected_outcomes={
            "detections_min": 1,
            "recommendations_min": 1,
            "engagements_min": 1,
            "chain_complete": True,
            "mission_completion_min": 100.0,
        },
    )

    return {
        s1.scenario_id: s1,
        s2.scenario_id: s2,
        s3.scenario_id: s3,
        s4.scenario_id: s4,
        s5.scenario_id: s5,
    }


_PREBUILT_SCENARIOS = _build_prebuilt_scenarios()


def get_prebuilt_scenarios() -> dict[str, ValidationScenario]:
    """Return all pre-built validation scenarios."""
    return dict(_PREBUILT_SCENARIOS)


def _build_adapters(platform_layout: Mapping[str, str]) -> dict[str, Any]:
    adapters: dict[str, Any] = {}
    for platform_id, platform_kind in platform_layout.items():
        kind = platform_kind.strip().lower()
        if kind == "hmmwv":
            adapter = HMMWVAdapter(platform_id)
        elif kind == "warwar":
            adapter = WarWarAdapter(platform_id)
            adapter.connect()
            adapter.launch()
            adapters[platform_id] = adapter
            continue
        elif kind == "g24":
            adapter = G24Adapter(platform_id)
        elif kind == "horizon":
            adapter = HorizonAdapter(platform_id)
        else:
            raise ValueError(f"unsupported platform kind: {platform_kind}")
        adapter.connect()
        adapters[platform_id] = adapter
    return adapters


def _write_sequences_to_json(
    scenario: ValidationScenario,
    output_dir: str | Path,
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for platform_id, records in scenario.telemetry_sequences.items():
        path = destination / f"{platform_id}.json"
        payload = {"platform_id": platform_id, "states": records}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        files[platform_id] = path
    return files


def run_validation_scenario(
    scenario: ValidationScenario,
    *,
    output_dir: str | Path | None = None,
    time_scale: int = 10,
    synchronize: bool = True,
) -> ScenarioOutcome:
    """Execute one pre-built validation scenario."""

    adapters = _build_adapters(scenario.platform_layout)
    replay_harness = TelemetryReplayHarness(adapters)
    track_store = TrackStore(association_distance_m=80.0, max_track_age_s=45.0)
    engagement_pipeline = EngagementPipeline()
    payload = RCWS127Adapter("rcws-validation")
    payload.connect()
    effectors = {"RCWS127": payload}

    aar = AARRecorder()
    aar.set_objective_total(scenario.objective_count)
    injector = FaultInjector(schedule=scenario.fault_schedule)

    managed_output_dir: TemporaryDirectory[str] | None = None
    if output_dir is None:
        managed_output_dir = TemporaryDirectory(prefix=f"{scenario.scenario_id}-")
        output_path = Path(managed_output_dir.name)
    else:
        output_path = Path(output_dir)
    telemetry_files = _write_sequences_to_json(scenario, output_path)
    for platform_id, path in telemetry_files.items():
        replay_harness.load_platform_state_sequence(path, platform_id=platform_id)

    counters = {
        "detections": 0,
        "handoffs": 0,
        "ais_contacts": 0,
        "recommendations": 0,
        "engagements": 0,
        "convoy_completed_count": 0,
    }
    completed_objectives: set[str] = set()

    detection_queue = sorted(scenario.detection_events, key=lambda event: event.sim_time_s)
    detection_idx = 0

    def _on_state_injected(platform_id: str, state: Any, sim_time_s: float) -> None:
        nonlocal detection_idx
        target = scenario.objective_positions.get(platform_id)
        if target is not None and platform_id not in completed_objectives:
            if math.dist(tuple(state.position), target) <= scenario.objective_tolerance_m:
                completed_objectives.add(platform_id)
                counters["convoy_completed_count"] = len(completed_objectives)
                aar.record_mission_event(
                    "objective_completed",
                    {
                        "objective": f"{platform_id}_arrived",
                        "platform_id": platform_id,
                        "sim_time_s": sim_time_s,
                    },
                )

        while detection_idx < len(detection_queue) and detection_queue[detection_idx].sim_time_s <= sim_time_s:
            detection = detection_queue[detection_idx]
            detection_idx += 1

            simulated_entity = SimEntity(
                entity_id=detection.track_id,
                entity_type=EntityType.ENEMY_UGV,
                position=detection.position,
                velocity=(0.0, 0.0, 0.0),
                heading=0.0,
                health=max(0.1, min(1.0, detection.confidence)),
            )

            track = Track(
                track_id=detection.track_id,
                position=simulated_entity.position,
                confidence=max(0.0, min(1.0, detection.confidence)),
                classification=detection.classification,
                threat_priority=detection.threat_priority,
            )
            track_store.ingest_track(track)

            counters["detections"] += 1
            if detection.classification.upper().startswith("AIS_"):
                counters["ais_contacts"] += 1
            if detection.handoff_to:
                counters["handoffs"] += 1
                aar.record_mission_event(
                    "track_handoff",
                    {
                        "track_id": detection.track_id,
                        "from_platform": detection.source_platform,
                        "to_platform": detection.handoff_to,
                        "sim_time_s": sim_time_s,
                    },
                )

            aar.record_mission_event(
                "detection",
                {
                    "track_id": detection.track_id,
                    "source_platform": detection.source_platform,
                    "classification": detection.classification,
                    "sim_time_s": sim_time_s,
                },
            )
            recommendations = engagement_pipeline.evaluate_threats(track_store.get_tracks(), effectors)
            for recommendation in recommendations:
                counters["recommendations"] += 1
                aar.record_engagement_pipeline_log(
                    "recommendation",
                    {
                        "track_id": recommendation.track_id,
                        "recommended_effector": recommendation.recommended_effector,
                        "roe_compliant": recommendation.roe_compliant,
                        "predicted_position": list(track.position),
                        "actual_position": list(detection.ground_truth_position or detection.position),
                    },
                )
                if recommendation.roe_compliant and recommendation.recommended_effector:
                    counters["engagements"] += 1
                    aar.record_decision(
                        "engage_decision",
                        {
                            "track_id": recommendation.track_id,
                            "rationale": recommendation.rationale,
                        },
                    )
                    aar.record_command(
                        {
                            "action": "engage",
                            "track_id": recommendation.track_id,
                            "effector": recommendation.recommended_effector,
                        },
                        platform_id=platform_id,
                    )
                    aar.record_safety_shell_audit(
                        "engagement_authorized",
                        {
                            "track_id": recommendation.track_id,
                            "roe_compliant": recommendation.roe_compliant,
                        },
                    )

    replay_summary = replay_harness.replay(
        time_scale=time_scale,
        synchronized=synchronize,
        realtime=False,
        fault_injector=injector,
        aar_recorder=aar,
        track_store=track_store,
        on_state_injected=_on_state_injected,
    )

    mission_completion_pct = round(
        (len(completed_objectives) / max(1, scenario.objective_count)) * 100.0,
        2,
    )
    if mission_completion_pct < 100.0 and scenario.objective_count > 0:
        aar.record_mission_event(
            "objective_failed",
            {
                "objective": "not_all_objectives_completed",
                "completed_count": len(completed_objectives),
                "objective_count": scenario.objective_count,
            },
        )
    aar.record_mission_event(
        "mission_completion",
        {
            "mission_completion_pct": mission_completion_pct,
            "completed_objectives": sorted(completed_objectives),
        },
    )

    metrics = aar.calculate_metrics()
    metrics["mission_completion_pct"] = mission_completion_pct
    markdown_aar = aar.generate_markdown_report(scenario.name)

    validation_errors = _validate_outcomes(
        expected=scenario.expected_outcomes,
        counters=counters,
        metrics=metrics,
    )
    replay_payload = {
        "platform_ids": replay_summary.platform_ids,
        "frame_count": replay_summary.frame_count,
        "injected_count": replay_summary.injected_count,
        "wall_duration_s": replay_summary.wall_duration_s,
        "sim_duration_s": replay_summary.sim_duration_s,
        "time_scale": replay_summary.time_scale,
        "synchronized": replay_summary.synchronized,
    }

    if managed_output_dir is not None:
        managed_output_dir.cleanup()

    return ScenarioOutcome(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        success=not validation_errors,
        metrics=metrics,
        counters=counters,
        validation_errors=validation_errors,
        replay_summary=replay_payload,
        markdown_aar=markdown_aar,
    )


def run_prebuilt_scenario(
    scenario_id: str,
    *,
    output_dir: str | Path | None = None,
    time_scale: int = 10,
    synchronize: bool = True,
) -> ScenarioOutcome:
    """Execute one scenario by identifier from pre-built library."""

    scenario = _PREBUILT_SCENARIOS.get(scenario_id)
    if scenario is None:
        raise KeyError(f"unknown scenario_id: {scenario_id}")
    return run_validation_scenario(
        scenario,
        output_dir=output_dir,
        time_scale=time_scale,
        synchronize=synchronize,
    )


def _validate_outcomes(
    *,
    expected: Mapping[str, Any],
    counters: Mapping[str, int],
    metrics: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if counters.get("detections", 0) < int(expected.get("detections_min", 0)):
        errors.append("detections below expected minimum")
    if counters.get("handoffs", 0) < int(expected.get("handoffs_min", 0)):
        errors.append("track handoffs below expected minimum")
    if counters.get("ais_contacts", 0) < int(expected.get("ais_contacts_min", 0)):
        errors.append("AIS contacts below expected minimum")
    if counters.get("recommendations", 0) < int(expected.get("recommendations_min", 0)):
        errors.append("engagement recommendations below expected minimum")
    if counters.get("engagements", 0) < int(expected.get("engagements_min", 0)):
        errors.append("engagement count below expected minimum")
    if bool(expected.get("convoy_arrived", False)) and counters.get("convoy_completed_count", 0) < 3:
        errors.append("convoy objective not completed for all vehicles")
    if bool(expected.get("chain_complete", False)):
        if counters.get("detections", 0) < 1 or counters.get("engagements", 0) < 1:
            errors.append("detect-track-engage chain did not complete")

    min_completion = float(expected.get("mission_completion_min", 0.0))
    completion = float(metrics.get("mission_completion_pct", 0.0))
    if completion < min_completion:
        errors.append(f"mission completion below threshold ({completion} < {min_completion})")
    return errors
