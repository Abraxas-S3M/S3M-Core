"""Dataset manifest registry for synthetic data provenance and integrity."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import hashlib
import json

from src.simulation.models import SyntheticDataset


class DatasetManifest:
    """Maintains metadata catalog of synthetic datasets for military traceability."""

    def __init__(self, manifest_dir: str = "data/manifests/") -> None:
        self.manifest_dir = Path(manifest_dir)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, dataset_id: str) -> Path:
        return self.manifest_dir / f"{dataset_id}.json"

    def register(self, dataset: SyntheticDataset) -> None:
        """Register dataset metadata in manifest directory."""
        self._path(dataset.dataset_id).write_text(json.dumps(dataset.to_dict(), indent=2), encoding="utf-8")

    def _from_payload(self, payload: dict) -> SyntheticDataset:
        return SyntheticDataset(
            dataset_id=str(payload["dataset_id"]),
            name=str(payload["name"]),
            description=str(payload["description"]),
            generator=str(payload["generator"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            record_count=int(payload["record_count"]),
            file_path=str(payload["file_path"]),
            file_size_bytes=int(payload["file_size_bytes"]),
            checksum_sha256=str(payload["checksum_sha256"]),
            schema=dict(payload.get("schema", {})),
            generation_params=dict(payload.get("generation_params", {})),
            license=str(payload.get("license", "S3M-INTERNAL")),
        )

    def get(self, dataset_id: str) -> Optional[SyntheticDataset]:
        """Get dataset metadata by dataset ID."""
        path = self._path(dataset_id)
        if not path.exists():
            return None
        return self._from_payload(json.loads(path.read_text(encoding="utf-8")))

    def list_datasets(self, generator: Optional[str] = None) -> List[SyntheticDataset]:
        """List all registered datasets, optionally filtered by generator name."""
        datasets: List[SyntheticDataset] = []
        for path in sorted(self.manifest_dir.glob("*.json")):
            try:
                dataset = self._from_payload(json.loads(path.read_text(encoding="utf-8")))
                if generator is not None and dataset.generator != generator:
                    continue
                datasets.append(dataset)
            except Exception:
                continue
        return datasets

    def verify(self, dataset_id: str) -> bool:
        """Recompute checksum and compare with manifest metadata."""
        dataset = self.get(dataset_id)
        if dataset is None:
            return False
        return self._compute_checksum(dataset.file_path) == dataset.checksum_sha256.lower()

    def _compute_checksum(self, filepath: str) -> str:
        digest = hashlib.sha256()
        path = Path(filepath)
        if not path.exists():
            return ""
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest().lower()

    def delete(self, dataset_id: str) -> None:
        """Delete manifest entry but preserve underlying data file."""
        path = self._path(dataset_id)
        if path.exists():
            path.unlink()

    def export_catalog(self, filepath: str) -> None:
        """Export full dataset catalog as JSON."""
        data = [dataset.to_dict() for dataset in self.list_datasets()]
        Path(filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")
