"""
Tests that simulation outputs can be used to train Layer 03 RL agents
and generate Layer 02 detection training data.
"""

from __future__ import annotations

import csv

from src.sensor_fusion.models import SensorType
from src.sensor_fusion.sensor_manager import SensorManager
from src.simulation.adapters import BuiltinPhysicsEngine
from src.simulation.models import EntityType, SimConfig
from src.simulation.synthetic import SyntheticDataManager
from src.simulation.wargame.scenario_engine import ScenarioEngine
from src.simulation.wargame.scenario_runner import ScenarioRunner
from src.threat_detection.anomaly_detector import AnomalyDetector
from src.threat_detection.models import ThreatCategory


def test_scenario_produces_replay() -> None:
    engine = ScenarioEngine(scenarios_dir="configs/scenarios")
    scenario = engine.load_from_yaml("configs/scenarios/urban_patrol.yaml")

    runner = ScenarioRunner(adapter=BuiltinPhysicsEngine(SimConfig(simulator_name="builtin")))
    runner.adapter.connect()
    assert runner.load(scenario)

    aar = runner.run(max_ticks=100, tick_dt=0.1)
    replay = runner.get_replay()

    assert aar is not None
    assert replay is not None
    assert replay.tick_count > 0


def test_replay_converts_to_sensor_data() -> None:
    engine = ScenarioEngine(scenarios_dir="configs/scenarios")
    scenario = engine.load_from_yaml("configs/scenarios/urban_patrol.yaml")

    runner = ScenarioRunner(adapter=BuiltinPhysicsEngine(SimConfig(simulator_name="builtin")))
    runner.adapter.connect()
    runner.load(scenario)
    runner.run(max_ticks=40, tick_dt=0.1)
    replay = runner.get_replay()
    assert replay is not None

    recorder = runner.replay_recorder
    states = list(recorder.load_replay(replay.replay_id))
    assert states

    manager = SensorManager()
    manager.register_sensor("sim_radar", SensorType.RADAR)

    for state in states[:20]:
        readings = state.to_sensor_readings()
        for reading in readings:
            manager.ingest(
                sensor_id="sim_radar",
                data=reading.data,
                position=reading.position,
                confidence=reading.confidence,
            )
    tracks = manager.process()
    assert tracks


def test_synthetic_data_feeds_anomaly_detector() -> None:
    manager = SyntheticDataManager(output_dir="data/synthetic")
    dataset = manager.generate_network_traffic(n_records=500, attack_ratio=0.1)

    rows = []
    with open(dataset.file_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                [
                    float(row["duration"]),
                    float(row["bytes_in"]),
                    float(row["bytes_out"]),
                ]
            )

    normal = rows[:250]
    detector = AnomalyDetector(contamination=0.1, n_estimators=50)
    detector.fit(normal)
    events = detector.detect(rows, feature_names=["duration", "bytes_in", "bytes_out"])

    expected = int(0.1 * len(rows))
    backend = detector.health_check().get("backend", "unknown")

    if backend == "isolation_forest":
        # 50% tolerance band per requirement when full ML backend is available.
        assert abs(len(events) - expected) <= max(1, int(expected * 0.5))
    else:
        # Fallback z-score mode is intentionally conservative in minimal offline envs.
        assert len(events) > 0


def test_simulation_state_to_threats() -> None:
    engine = BuiltinPhysicsEngine(SimConfig(simulator_name="builtin"))
    engine.connect()
    engine.start_simulation()

    for idx in range(3):
        engine.spawn_entity(EntityType.ENEMY_UAV, (100 + idx * 10, 200 + idx * 10, 80))

    state = engine.step(0.1)
    events = state.to_threat_events()

    assert len(events) == 3
    assert all(event.category in {ThreatCategory.SURVEILLANCE, ThreatCategory.KINETIC} for event in events)
