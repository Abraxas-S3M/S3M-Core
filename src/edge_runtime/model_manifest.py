"""
Per-model manifest loader for austere tactical edge deployments.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

LOGGER = logging.getLogger("s3m.edge_runtime.manifest")


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
    estimated_tps_gpu: float = 0.0


class ModelManifest:
    """
    Hybrid manifest object that preserves both codepaths:
    - object-oriented manifest usage (`load`, `load_all`, `get_best_cpu_variant`)
    - dictionary-style lookup helpers (`get_manifest`, `validate_thresholds`)
    """

    def __init__(
        self,
        model_id: str,
        model_name: str,
        variants: List[ManifestVariant],
        runtime_backend: str = "llama_cpp",
        training: Optional[Dict[str, object]] = None,
        thresholds: Optional[Dict[str, object]] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.model_id = model_id
        self.model_name = model_name
        self.variants = list(variants)
        self.runtime_backend = str(runtime_backend)
        self.training = dict(training or {})
        self.thresholds = dict(thresholds or {})
        self.raw_payload = dict(raw_payload or {})

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
            except Exception as exc:
                LOGGER.warning("Skipping invalid manifest %s: %s", path, exc)
                continue
            loaded[manifest.model_id] = manifest
        return loaded

    @classmethod
    def _from_file(cls, path: Path) -> "ModelManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Manifest must be a mapping: {path}")
        model_id = str(data.get("model_id") or path.stem)
        model_name = str(data.get("model_name") or model_id)
        runtime_backend = str(data.get("runtime_backend", "llama_cpp"))
        raw_variants = list(data.get("variants") or [])

        variants: List[ManifestVariant] = []
        for item in raw_variants:
            if not isinstance(item, dict):
                continue
            variant_tag = str(item.get("variant_tag") or item.get("tag") or "default")
            file_path = str(item.get("file_path") or item.get("file") or "")
            min_ram_gb = float(item.get("min_ram_gb") or (float(item.get("max_ram_mb") or 0.0) / 1024.0))
            variants.append(
                ManifestVariant(
                    model_id=model_id,
                    variant_tag=variant_tag,
                    file_path=file_path,
                    runtime_format=str(item.get("runtime_format") or "gguf"),
                    precision=str(item.get("precision") or "int4"),
                    size_mb=float(item.get("size_mb") or 0.0),
                    min_ram_gb=min_ram_gb,
                    requires_gpu=bool(item.get("requires_gpu", False)),
                    max_context=int(item.get("max_context") or 4096),
                    estimated_tps_cpu=float(item.get("estimated_tps_cpu") or item.get("cpu_tokens_per_sec") or 0.0),
                    estimated_tps_gpu=float(item.get("estimated_tps_gpu") or item.get("gpu_tokens_per_sec") or 0.0),
                )
            )

        thresholds = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
        quality = data.get("quality_thresholds")
        if isinstance(quality, dict):
            thresholds = {**thresholds, **quality}
        training = data.get("training") if isinstance(data.get("training"), dict) else {}
        if "adapter_tuning_allowed" in data:
            training = {**training, "adapter_tuning_allowed": bool(data.get("adapter_tuning_allowed"))}

        return cls(
            model_id=model_id,
            model_name=model_name,
            variants=variants,
            runtime_backend=runtime_backend,
            training=training,
            thresholds=thresholds,
            raw_payload=data,
        )

    def get_manifest(self, model_id: str) -> dict:
        if self.model_id == str(model_id).strip():
            payload = dict(self.raw_payload)
            if "model_id" not in payload:
                payload["model_id"] = self.model_id
            return payload
        return {}

    def get_variant(self, variant_tag: str) -> Optional[ManifestVariant]:
        requested = str(variant_tag).strip()
        for variant in self.variants:
            if variant.variant_tag == requested:
                return variant
        return None

    def get_cpu_variants(self, model_id: str) -> list[dict]:
        if self.model_id != str(model_id).strip():
            return []
        return [
            {
                "tag": variant.variant_tag,
                "runtime_format": variant.runtime_format,
                "file": variant.file_path,
                "size_mb": variant.size_mb,
                "max_ram_mb": round(float(variant.min_ram_gb) * 1024.0, 2),
                "cpu_tokens_per_sec": variant.estimated_tps_cpu,
                "gpu_tokens_per_sec": variant.estimated_tps_gpu,
                "requires_gpu": variant.requires_gpu,
                "max_context": variant.max_context,
            }
            for variant in self.variants
            if not variant.requires_gpu
        ]

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

        return sorted(candidates, key=lambda item: (item.size_mb, -item.estimated_tps_cpu))[0]

    def get_export_targets(self, model_id: str) -> list[str]:
        payload = self.get_manifest(model_id)
        if not payload:
            return []
        return list(payload.get("export_targets", []))

    def validate_threshold(self, threshold_key: str, value: object) -> bool:
        limit = self.thresholds.get(threshold_key)
        if limit is None:
            return True
        if isinstance(limit, (int, float)) and isinstance(value, (int, float)):
            return float(value) <= float(limit)
        return True

    def validate_thresholds(
        self,
        model_id: str,
        latency_ms: float,
        memory_mb: float,
        accuracy_pct: float,
    ) -> dict:
        if self.model_id != str(model_id).strip():
            return {"pass": False, "error": "model_manifest_not_found", "model_id": model_id}
        min_acc = float(self.thresholds.get("min_accuracy_pct", 0.0))
        max_latency = float(self.thresholds.get("max_latency_p95_ms", float("inf")))
        max_memory = float(self.thresholds.get("max_memory_mb", float("inf")))
        accuracy_ok = float(accuracy_pct) >= min_acc
        latency_ok = float(latency_ms) <= max_latency
        memory_ok = float(memory_mb) <= max_memory
        return {
            "pass": bool(accuracy_ok and latency_ok and memory_ok),
            "accuracy_ok": bool(accuracy_ok),
            "latency_ok": bool(latency_ok),
            "memory_ok": bool(memory_ok),
            "model_id": model_id,
            "measured": {
                "latency_ms": float(latency_ms),
                "memory_mb": float(memory_mb),
                "accuracy_pct": float(accuracy_pct),
            },
            "thresholds": {
                "min_accuracy_pct": min_acc,
                "max_latency_p95_ms": max_latency,
                "max_memory_mb": max_memory,
            },
        }

    def is_adapter_tuning_allowed(self) -> bool:
        return bool(self.training.get("adapter_tuning_allowed", False))
