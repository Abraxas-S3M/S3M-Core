#!/usr/bin/env python3
"""Tests for synthetic tabular data generation."""

from __future__ import annotations

from pathlib import Path

from src.simulation.synthetic.tabular_generator import TabularGenerator


def test_generate_network_traffic_columns_and_count():
    generator = TabularGenerator(backend="numpy")
    payload = generator.generate_network_traffic(n_records=200, attack_ratio=0.2)
    assert len(payload["data"]) == 200
    assert payload["columns"] == [
        "timestamp",
        "src_ip",
        "dst_ip",
        "src_port",
        "dst_port",
        "protocol",
        "duration",
        "bytes_in",
        "bytes_out",
        "packets",
        "label",
        "attack_type",
    ]


def test_attack_ratio_approximate():
    generator = TabularGenerator(backend="numpy")
    payload = generator.generate_network_traffic(n_records=1000, attack_ratio=0.15)
    ratio = payload["stats"]["attack_ratio_actual"]
    assert 0.08 <= ratio <= 0.22


def test_generate_sensor_telemetry_multi_sensor():
    generator = TabularGenerator(backend="numpy")
    payload = generator.generate_sensor_telemetry(n_records=300, n_sensors=6, anomaly_ratio=0.1)
    assert len(payload["data"]) == 300
    sensor_ids = {row[0] for row in payload["data"]}
    assert len(sensor_ids) >= 3


def test_generate_logistics_data_valid_records():
    generator = TabularGenerator(backend="numpy")
    payload = generator.generate_logistics_data(n_records=120)
    assert len(payload["data"]) == 120
    assert all(len(row) == len(payload["columns"]) for row in payload["data"])


def test_save_csv_creates_file(tmp_path: Path):
    generator = TabularGenerator(backend="numpy")
    payload = generator.generate_network_traffic(n_records=20, attack_ratio=0.2)
    output = tmp_path / "net.csv"
    path = generator.save_csv(payload, str(output))
    assert path == str(output)
    assert output.exists()
