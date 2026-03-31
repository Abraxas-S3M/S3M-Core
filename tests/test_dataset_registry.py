from __future__ import annotations

import csv

from src.apps.data_management.data_loader import DataLoader
from src.apps.data_management.dataset_registry import DatasetRegistry


def test_load_registry_reads_yaml():
    registry = DatasetRegistry("configs/datasets/registry.yaml")
    assert len(registry.list_datasets()) >= 32


def test_list_datasets_count():
    registry = DatasetRegistry("configs/datasets/registry.yaml")
    datasets = registry.list_datasets()
    assert len(datasets) == 32


def test_list_datasets_domain_filter():
    registry = DatasetRegistry("configs/datasets/registry.yaml")
    military = registry.list_datasets(domain="military")
    assert military
    assert all(item["domain"] == "military" for item in military)


def test_get_dataset_detail():
    registry = DatasetRegistry("configs/datasets/registry.yaml")
    dataset = registry.get_dataset("DAT-001")
    assert dataset is not None
    assert dataset["name"]
    assert dataset["dataset_id"] == "DAT-001"


def test_check_availability_missing_default():
    registry = DatasetRegistry("configs/datasets/registry.yaml")
    status = registry.check_availability()
    assert status["total"] == 32
    assert status["missing"] >= 1
    assert all(item.get("available") is False or item.get("available") is True for item in status["datasets"])


def test_data_loader_csv_and_schema(tmp_path):
    path = tmp_path / "sample.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "delay_hours", "priority"])
        writer.writerow(["S1", "2.5", "3"])
        writer.writerow(["S2", "0.0", "1"])
    loader = DataLoader()
    result = loader.load_csv(str(path))
    assert result["records"] == 2
    assert result["columns"] == ["id", "delay_hours", "priority"]
    schema = loader.get_schema(str(path))
    assert "columns" in schema and len(schema["columns"]) == 3
