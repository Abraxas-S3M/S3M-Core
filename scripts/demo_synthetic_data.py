#!/usr/bin/env python3
"""Phase 7 synthetic data generation demonstration."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.synthetic import SyntheticDataManager


def main() -> None:
    manager = SyntheticDataManager()
    datasets = [
        manager.generate_network_traffic(n_records=500, attack_ratio=0.15),
        manager.generate_sensor_telemetry(n_records=300, n_sensors=5, anomaly_ratio=0.07),
        manager.generate_logistics_data(n_records=150),
        manager.generate_uav_trajectories(n_agents=3, duration=60.0),
        manager.generate_threat_scenarios(n_scenarios=3, events_per=40),
    ]

    print("Generated datasets:")
    for dataset in datasets:
        print("-", dataset.dataset_id, dataset.name, dataset.generator, dataset.record_count)
        print("  file:", dataset.file_path)
        print("  checksum valid:", manager.verify_dataset(dataset.dataset_id))
        print("  schema:", json.dumps(dataset.schema, indent=2)[:200], "...")

    catalog = manager.list_datasets()
    print("\nManifest catalog size:", len(catalog))
    print("Stats:", manager.get_stats())


if __name__ == "__main__":
    main()
