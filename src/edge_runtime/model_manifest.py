"""
Model manifest loader for CPU-first edge deployments.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass(frozen=True)
class ManifestVariant:
    model_id: str
    variant_tag: str
    file_path: str
    runtime_format: str = "gguf"
    precision: str = "int4"
    size_mb: float = 0.0
    min_ram_gb: float = 0.0
    requires_gpu: bool = False
    max_context: int = 4096
    estimated_tps_cpu: float = 0.0


class ModelManifest:
    """
    Loads model-level deployment policy and variants from YAML.

    Tactical context:
    Manifest policy is treated as the mission-authoritative contract for what
    can run locally on disconnected and CPU-constrained nodes.
    """

    def __init__(
        self,
        model_id: str,
        model_name: str,
        variants: List[ManifestVariant],
        runtime_backend: str = "llama_cpp",
        training: Optional[Dict[str, object]] = None,
        thresholds: Optional[Dict[str, object]] = None,
    ) -> None:
        self.model_id = model_id
        self.model_name = model_name
        self.variants = list(variants)
        self.runtime_backend = str(runtime_backend)
        self.training = dict(training or {})
        self.thresholds = dict(thresholds or {})

    @classmethod
    def load(cls, model_id: str, manifest_dir: str = "configs/model_manifests") -> "ModelManifest":
        manifest_root = Path(manifest_dir)
        if not manifest_root.exists():
            raise FileNotFoundError(f"Manifest directory not found: {manifest_root}")

        normalized = str(model_id).strip()
        candidate_names = [
            f"{normalized}.yaml",
            f"{normalized}.yml",
            f"{normalized.replace('-', '_')}.yaml",
            f"{normalized.replace('-', '_')}.yml",
        ]
        for candidate in candidate_names:
            candidate_path = manifest_root / candidate
            if candidate_path.exists():
                return cls._from_file(candidate_path)

        for path in sorted(manifest_root.glob("*.y*ml")):
            manifest = cls._from_file(path)
            if manifest.model_id == normalized:
                return manifest

        raise FileNotFoundError(f"No manifest found for model_id='{normalized}' in {manifest_root}")

    @classmethod
    def load_all(cls, manifest_dir: str = "configs/model_manifests") -> Dict[str, "ModelManifest"]:
        manifest_root = Path(manifest_dir)
        if not manifest_root.exists():
            return {}
        loaded: Dict[str, ModelManifest] = {}
        for path in sorted(manifest_root.glob("*.y*ml")):
            try:
                manifest = cls._from_file(path)
            except Exception:
                continue
            loaded[manifest.model_id] = manifest
        return loaded

    @classmethod
    def _from_file(cls, path: Path) -> "ModelManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        model_id = str(data.get("model_id") or path.stem)
        model_name = str(data.get("model_name") or model_id)
        runtime_backend = str(data.get("runtime_backend", "llama_cpp"))
        raw_variants = list(data.get("variants") or [])

        variants: List[ManifestVariant] = []
        for item in raw_variants:
            if not isinstance(item, dict):
                continue
            variant_tag = str(item.get("variant_tag") or "default")
            variants.append(
                ManifestVariant(
                    model_id=model_id,
                    variant_tag=variant_tag,
                    file_path=str(item.get("file_path") or ""),
                    runtime_format=str(item.get("runtime_format") or "gguf"),
                    precision=str(item.get("precision") or "int4"),
                    size_mb=float(item.get("size_mb") or 0.0),
                    min_ram_gb=float(item.get("min_ram_gb") or 0.0),
                    requires_gpu=bool(item.get("requires_gpu", False)),
                    max_context=int(item.get("max_context") or 4096),
                    estimated_tps_cpu=float(item.get("estimated_tps_cpu") or 0.0),
                )
            )

        return cls(
            model_id=model_id,
            model_name=model_name,
            variants=variants,
            runtime_backend=runtime_backend,
            training=data.get("training") if isinstance(data.get("training"), dict) else {},
            thresholds=data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {},
        )

    def get_variant(self, variant_tag: str) -> Optional[ManifestVariant]:
        requested = str(variant_tag).strip()
        for variant in self.variants:
            if variant.variant_tag == requested:
                return variant
        return None

    def get_best_cpu_variant(
        self,
        variant_tag: Optional[str] = None,
        available_ram_gb: Optional[float] = None,
    ) -> ManifestVariant:
        if variant_tag:
            tagged = self.get_variant(variant_tag)
            if tagged is None:
                raise ValueError(f"Unknown variant '{variant_tag}' for model '{self.model_id}'")
            candidates = [tagged]
        else:
            candidates = [variant for variant in self.variants if not variant.requires_gpu]

        if available_ram_gb is not None:
            fitting = [variant for variant in candidates if variant.min_ram_gb <= float(available_ram_gb)]
            if fitting:
                candidates = fitting

        if not candidates:
            raise ValueError(f"No CPU-capable variants found for model '{self.model_id}'")

        return sorted(candidates, key=lambda item: (item.size_mb, item.min_ram_gb))[0]

    def is_adapter_tuning_allowed(self) -> bool:
        return bool(self.training.get("adapter_tuning_allowed", False))

    def validate_threshold(self, threshold_key: str, value: object) -> bool:
        limit = self.thresholds.get(threshold_key)
        if limit is None:
            return True
        if isinstance(limit, (int, float)) and isinstance(value, (int, float)):
            return float(value) <= float(limit)
        return True
