"""Tests for closed-range validation harness components and scenarios."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from src.platforms.fixed.horizon_adapter import TrackStore
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.validation.aar_recorder import AARRecorder
from src.validation.fault_injector import FaultInjector, FaultScheduleEntry, FaultType, ScheduleMode
from src.validation.replay_harness import SUPPORTED_TIME_SCALES, TelemetryReplayHarness
from src.validation.scenarios import get_prebuilt_scenarios, run_prebuilt_scenario


def _write_sequence(path: Path, platform_id: str, platform_type: str, positions: list[tuple[float, float, float]]) -> None:
    payload = {
        "platform_id": platform_id,
        "states": [
            {
                "platform_id": platform_id,
                "platform_type": platform_type,
                "sim_time_s": float(idx),
                "position": list(position),
                "health_state": "nominal",
                "autonomy_mode": "supervised",
            }
            for idx, position in enumerate(positions)
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_replay_harness_replays_synchronized_platform_timelines(tmp_path: Path) -> None:
    adapter_a = HMMWVAdapter("hmmwv-a")
    adapter_b = HMMWVAdapter("hmmwv-b")
    adapter_a.connect()
    adapter_b.connect()
    harness = TelemetryReplayHarness({"hmmwv-a": adapter_a, "hmmwv-b": adapter_b})

    file_a = tmp_path / "a.json"
    file_b = tmp_path / "b.json"
    _write_sequence(file_a, "hmmwv-a", "ugv", [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)])
    _write_sequence(file_b, "hmmwv-b", "ugv", [(0.0, 5.0, 0.0), (10.0, 5.0, 0.0)])
    harness.load_platform_state_sequence(file_a, platform_id="hmmwv-a")
    harness.load_platform_state_sequence(file_b, platform_id="hmmwv-b")

    summary = harness.replay(time_scale=2, synchronized=True, realtime=False)
    assert summary.time_scale in SUPPORTED_TIME_SCALES
    assert summary.synchronized is True
    assert summary.frame_count == 4
    assert summary.injected_count == 4
    assert getattr(adapter_a, "_position") == (10.0, 0.0, 0.0)
    assert getattr(adapter_b, "_position") == (10.0, 5.0, 0.0)


def test_fault_injector_supports_all_fault_modes() -> None:
    adapter = HMMWVAdapter("fault-hmmwv")
    adapter.connect()
    harness = TelemetryReplayHarness({"fault-hmmwv": adapter})
    state = adapter.read_state()
    track_store = TrackStore()

    schedule = [
        FaultScheduleEntry(
            entry_id="sensor-periodic",
            fault_type=FaultType.SENSOR_DROPOUT,
            schedule_mode=ScheduleMode.PERIODIC,
            start_time_s=0.0,
            duration_s=2.0,
            interval_s=10.0,
            target_platforms=["fault-hmmwv"],
            config={"dropout_count": 2, "sensors": ["radar", "eo", "ir"]},
        ),
        FaultScheduleEntry(
            entry_id="link-periodic",
            fault_type=FaultType.LINK_LOSS,
            schedule_mode=ScheduleMode.PERIODIC,
            start_time_s=0.0,
            duration_s=2.0,
            interval_s=10.0,
            target_platforms=["fault-hmmwv"],
        ),
        FaultScheduleEntry(
            entry_id="gps-triggered",
            fault_type=FaultType.GPS_SPOOF,
            schedule_mode=ScheduleMode.TRIGGERED,
            start_time_s=0.0,
            duration_s=2.0,
            interval_s=10.0,
            trigger_key="spoof",
            target_platforms=["fault-hmmwv"],
            config={"false_coordinates": [999.0, 777.0, 0.0]},
        ),
        FaultScheduleEntry(
            entry_id="stale-random",
            fault_type=FaultType.STALE_TRACKS,
            schedule_mode=ScheduleMode.RANDOM,
            start_time_s=0.0,
            duration_s=1.0,
            interval_s=1.0,
            probability=1.0,
            config={"stale_count": 2},
        ),
        FaultScheduleEntry(
            entry_id="cpu-periodic",
            fault_type=FaultType.CPU_OVERLOAD,
            schedule_mode=ScheduleMode.PERIODIC,
            start_time_s=0.0,
            duration_s=1.0,
            interval_s=10.0,
            target_platforms=["fault-hmmwv"],
            config={"delay_s": 0.001, "method_names": ["read_state"]},
        ),
    ]
    injector = FaultInjector(schedule=schedule, random_seed=3)

    events = injector.run_scheduled_injections(
        sim_time_s=0.0,
        adapters={"fault-hmmwv": adapter},
        platform_states={"fault-hmmwv": state},
        track_store=track_store,
        trigger_flags={"spoof": True},
    )
    fault_types = {event["fault_type"] for event in events}
    assert FaultType.SENSOR_DROPOUT.value in fault_types
    assert FaultType.LINK_LOSS.value in fault_types
    assert FaultType.GPS_SPOOF.value in fault_types
    assert FaultType.STALE_TRACKS.value in fault_types
    assert FaultType.CPU_OVERLOAD.value in fault_types

    mutated_state = injector.apply_active_effects(platform_id="fault-hmmwv", state=state, sim_time_s=0.5)
    assert getattr(mutated_state, "comms_status") == "lost"
    assert tuple(mutated_state.position) == (999.0, 777.0, 0.0)
    assert len(track_store.get_tracks()) >= 1

    # Expire active faults and verify the injector can cleanly advance time.
    injector.run_scheduled_injections(
        sim_time_s=20.0,
        adapters={"fault-hmmwv": adapter},
        platform_states={"fault-hmmwv": state},
        track_store=track_store,
        trigger_flags={},
    )
    assert isinstance(adapter.read_state().platform_id, str)
    assert isinstance(harness.adapters["fault-hmmwv"], HMMWVAdapter)


def test_aar_recorder_generates_metrics_and_markdown() -> None:
    recorder = AARRecorder()
    recorder.set_objective_total(2)
    recorder.record_mission_event("detection", {"track_id": "trk-1"})
    recorder.record_decision("engage_decision", {"track_id": "trk-1"})
    recorder.record_command({"action": "engage", "track_id": "trk-1"}, platform_id="hmmwv-1")
    recorder.record_engagement_pipeline_log(
        "recommendation",
        {
            "track_id": "trk-1",
            "predicted_position": [100.0, 100.0, 0.0],
            "actual_position": [102.0, 101.0, 0.0],
        },
    )
    recorder.record_fault("link_loss", {"platform_id": "hmmwv-1"})
    recorder.record_safety_shell_audit("engagement_authorized", {"track_id": "trk-1"})
    recorder.record_mission_event("objective_completed", {"objective": "obj-1"})
    recorder.record_mission_event("objective_failed", {"objective": "obj-2"})

    metrics = recorder.calculate_metrics()
    assert metrics["mission_completion_pct"] == 50.0
    assert metrics["reaction_time_s"] is not None
    assert metrics["track_accuracy_pct"] == 100.0

    markdown = recorder.generate_markdown_report("Validation Mission")
    assert "After Action Review" in markdown
    assert "Safety Shell Audit Log" in markdown


@pytest.mark.parametrize(
    "scenario_id",
    [
        "scenario_1_hmmwv_patrol",
        "scenario_2_warwar_isr_handoff",
        "scenario_3_g24_maritime_patrol",
        "scenario_4_hmmwv_convoy_overwatch",
        "scenario_5_full_hool_chain",
    ],
)
def test_prebuilt_validation_scenarios_meet_expected_outcomes(tmp_path: Path, scenario_id: str) -> None:
    scenarios = get_prebuilt_scenarios()
    assert scenario_id in scenarios
    outcome = run_prebuilt_scenario(
        scenario_id,
        output_dir=tmp_path / scenario_id,
        time_scale=10,
        synchronize=True,
    )
    assert outcome.success, outcome.validation_errors
    expected_completion = scenarios[scenario_id].expected_outcomes.get("mission_completion_min", 0.0)
    assert float(outcome.metrics.get("mission_completion_pct", 0.0)) >= float(expected_completion)
    assert len(outcome.markdown_aar) > 0
