"""Coordinator for Layer 04 synthetic dataset generation workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from uuid import uuid4
import hashlib
import json

from src.simulation.models import SyntheticDataset
from src.simulation.synthetic.dataset_manifest import DatasetManifest
from src.simulation.synthetic.scenario_data_generator import ScenarioDataGenerator
from src.simulation.synthetic.tabular_generator import TabularGenerator
from src.simulation.synthetic.trajectory_generator import TrajectoryGenerator


class SyntheticDataManager:
    """Orchestrates all synthetic generators for multi-layer S3M training data."""

    def __init__(self, output_dir: str = "data/synthetic/") -> None:
        if not isinstance(output_dir, str) or not output_dir.strip():
            raise ValueError("output_dir must be a non-empty string")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tabular = TabularGenerator()
        self.trajectory = TrajectoryGenerator()
        self.scenario = ScenarioDataGenerator()
        self.manifest = DatasetManifest()

    def _checksum(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _register(
        self,
        name: str,
        description: str,
        generator: str,
        file_path: Path,
        record_count: int,
        schema: Dict[str, str],
        generation_params: Dict[str, object],
    ) -> SyntheticDataset:
        dataset = SyntheticDataset(
            dataset_id=str(uuid4()),
            name=name,
            description=description,
            generator=generator,
            created_at=datetime.now(timezone.utc),
            record_count=record_count,
            file_path=str(file_path),
            file_size_bytes=file_path.stat().st_size,
            checksum_sha256=self._checksum(file_path),
            schema=schema,
            generation_params=generation_params,
            license="S3M-INTERNAL",
        )
        self.manifest.register(dataset)
        return dataset

    def generate_network_traffic(self, n_records: int, attack_ratio: float) -> SyntheticDataset:
        data = self.tabular.generate_network_traffic(n_records=n_records, attack_ratio=attack_ratio)
        path = self.output_dir / f"network_{uuid4().hex[:8]}.csv"
        self.tabular.save_csv(data, str(path))
        schema = {col: "string" for col in data["columns"]}
        return self._register(
            name="Synthetic Network Traffic",
            description="Synthetic CIC-IDS-style traffic for cyber threat training.",
            generator="tabular",
            file_path=path,
            record_count=len(data["data"]),
            schema=schema,
            generation_params={"n_records": n_records, "attack_ratio": attack_ratio},
        )

    def generate_sensor_telemetry(self, n_records: int, n_sensors: int, anomaly_ratio: float) -> SyntheticDataset:
        data = self.tabular.generate_sensor_telemetry(
            n_records=n_records,
            n_sensors=n_sensors,
            anomaly_ratio=anomaly_ratio,
        )
        path = self.output_dir / f"sensor_{uuid4().hex[:8]}.csv"
        self.tabular.save_csv(data, str(path))
        schema = {col: "string" for col in data["columns"]}
        return self._register(
            name="Synthetic Sensor Telemetry",
            description="Synthetic platform sensor health data for anomaly pipeline testing.",
            generator="tabular",
            file_path=path,
            record_count=len(data["data"]),
            schema=schema,
            generation_params={"n_records": n_records, "n_sensors": n_sensors, "anomaly_ratio": anomaly_ratio},
        )

    def generate_logistics_data(self, n_records: int) -> SyntheticDataset:
        data = self.tabular.generate_logistics_data(n_records=n_records)
        path = self.output_dir / f"logistics_{uuid4().hex[:8]}.csv"
        self.tabular.save_csv(data, str(path))
        schema = {col: "string" for col in data["columns"]}
        return self._register(
            name="Synthetic Logistics Data",
            description="Synthetic convoy and shipment records for planning rehearsals.",
            generator="tabular",
            file_path=path,
            record_count=len(data["data"]),
            schema=schema,
            generation_params={"n_records": n_records},
        )

    def generate_uav_trajectories(self, n_agents: int, duration: float) -> SyntheticDataset:
        trajectories = self.trajectory.generate_swarm_trajectories(n_agents=n_agents, duration=duration)
        path = self.output_dir / f"uav_trajectories_{uuid4().hex[:8]}.json"
        self.trajectory.save_trajectories(trajectories, str(path))
        records = sum(len(v) for v in trajectories.values())
        return self._register(
            name="Synthetic UAV Trajectories",
            description="Swarm trajectory records for autonomy and navigation validation.",
            generator="trajectory",
            file_path=path,
            record_count=records,
            schema={"agent_id": "string", "trajectory_records": "array"},
            generation_params={"n_agents": n_agents, "duration": duration},
        )

    def generate_threat_scenarios(self, n_scenarios: int, events_per: int) -> SyntheticDataset:
        benchmark = self.scenario.generate_detection_benchmark(
            n_scenarios=n_scenarios,
            events_per_scenario=events_per,
        )
        path = self.output_dir / f"threat_scenarios_{uuid4().hex[:8]}.json"
        self.scenario.save_scenarios(benchmark, str(path))
        return self._register(
            name="Synthetic Threat Scenarios",
            description="Labeled threat-event scenarios for detection benchmark regression.",
            generator="scenario",
            file_path=path,
            record_count=int(benchmark.get("total_records", len(benchmark.get("records", [])))),
            schema={
                "timestamp": "string",
                "threat_source": "string",
                "threat_level": "string",
                "threat_category": "string",
                "position": "array",
                "ground_truth_label": "boolean",
            },
            generation_params={"n_scenarios": n_scenarios, "events_per_scenario": events_per},
        )

    def generate_full_training_bundle(self) -> List[SyntheticDataset]:
        """Generate one complete synthetic package for integrated training drills."""
        return [
            self.generate_network_traffic(n_records=10_000, attack_ratio=0.1),
            self.generate_sensor_telemetry(n_records=5_000, n_sensors=10, anomaly_ratio=0.05),
            self.generate_logistics_data(n_records=2_000),
            self.generate_uav_trajectories(n_agents=4, duration=120.0),
            self.generate_threat_scenarios(n_scenarios=10, events_per=100),
        ]

    def list_datasets(self) -> List[SyntheticDataset]:
        return self.manifest.list_datasets()

    def verify_dataset(self, dataset_id: str) -> bool:
        return self.manifest.verify(dataset_id)

    def get_stats(self) -> dict:
        datasets = self.list_datasets()
        by_generator: Dict[str, int] = {}
        total_size = 0
        for dataset in datasets:
            by_generator[dataset.generator] = by_generator.get(dataset.generator, 0) + 1
            total_size += dataset.file_size_bytes
        return {
            "total_datasets": len(datasets),
            "total_size_bytes": total_size,
            "by_generator": by_generator,
        }
