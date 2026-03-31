"""Dataset registry for Phase 11 data management workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.apps._shared import ensure_non_empty_text, summarize_counts


class DatasetRegistry:
    """Load and query dataset metadata for offline acquisition workflows."""

    def __init__(self, registry_path: str = "configs/datasets/registry.yaml") -> None:
        self.registry_path = Path(ensure_non_empty_text(registry_path, "registry_path"))
        self._registry: dict[str, Any] = {"datasets": []}
        self.load_registry()

    def load_registry(self) -> None:
        if not self.registry_path.exists():
            self._registry = {"datasets": []}
            return
        with self.registry_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        datasets = payload.get("datasets", [])
        if not isinstance(datasets, list):
            datasets = []
        self._registry = {"datasets": datasets}

    def list_datasets(self, domain: str = None) -> List[dict]:
        datasets: list[dict] = []
        domain_filter = domain.strip().lower() if isinstance(domain, str) and domain.strip() else None
        for entry in self._registry.get("datasets", []):
            if not isinstance(entry, dict):
                continue
            if domain_filter and str(entry.get("domain", "")).lower() != domain_filter:
                continue
            item = dict(entry)
            local_path = str(item.get("local_path", ""))
            item["dataset_id"] = item.get("id")
            item["available"] = bool(local_path and Path(local_path).exists())
            datasets.append(item)
        return datasets

    def get_dataset(self, dataset_id: str) -> Optional[dict]:
        target = ensure_non_empty_text(dataset_id, "dataset_id")
        for dataset in self.list_datasets():
            if str(dataset.get("dataset_id")) == target or str(dataset.get("id")) == target:
                return dataset
        return None

    def check_availability(self) -> dict:
        datasets = self.list_datasets()
        available = [item for item in datasets if item.get("available")]
        missing = [item for item in datasets if not item.get("available")]
        return {
            "total": len(datasets),
            "available": len(available),
            "missing": len(missing),
            "datasets": datasets,
        }

    def get_download_instructions(self, dataset_id: str) -> str:
        dataset = self.get_dataset(dataset_id)
        if dataset is None:
            raise ValueError(f"Unknown dataset_id: {dataset_id}")
        instructions = str(dataset.get("download_instructions", "")).strip()
        return (
            "Air-gapped acquisition required: download on internet-connected machine, "
            "transfer via secure media. " + instructions
        )

    def get_stats(self) -> dict:
        datasets = self.list_datasets()
        by_domain = summarize_counts(datasets, "domain")
        by_format = summarize_counts(datasets, "format")
        available_count = sum(1 for item in datasets if item.get("available"))
        return {
            "total": len(datasets),
            "by_domain": by_domain,
            "by_format": by_format,
            "available": available_count,
            "missing": len(datasets) - available_count,
        }
