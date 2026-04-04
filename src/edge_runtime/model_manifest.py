"""
Per-model manifest loader for austere tactical edge deployments.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
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


@dataclass
class ModelManifestRecord:
    """Object-oriented manifest record used by planner/inference/orchestrator."""

    model_id: str
    model_name: str
    variants: List[ManifestVariant]
    runtime_backend: str = "llama_cpp"
    training: Optional[Dict[str, object]] = None
    thresholds: Optional[Dict[str, object]] = None
    raw_payload: Optional[Dict[str, Any]] = None

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

        return sorted(candidates, key=lambda item: (-item.estimated_tps_cpu, item.size_mb))[0]

    def is_adapter_tuning_allowed(self) -> bool:
        return bool((self.training or {}).get("adapter_tuning_allowed", False))

    def validate_threshold(self, threshold_key: str, value: object) -> bool:
        limit = (self.thresholds or {}).get(threshold_key)
        if limit is None:
            return True
        if isinstance(limit, (int, float)) and isinstance(value, (int, float)):
            return float(value) <= float(limit)
        return True


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _variant_from_payload(model_id: str, item: dict[str, Any]) -> ManifestVariant:
    variant_tag = str(item.get("variant_tag") or item.get("tag") or "default")
    file_path = str(item.get("file_path") or item.get("file") or "")
    min_ram_gb = float(item.get("min_ram_gb") or (float(item.get("max_ram_mb") or 0.0) / 1024.0))
    return ManifestVariant(
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


class _ManifestLoader:
    """Dictionary-style loader retained for existing manifest tests."""

    def __init__(self, manifest_dir: str = "configs/model_manifests") -> None:
        self.manifest_dir = Path(manifest_dir)
        self._cache: dict[str, dict[str, Any]] | None = None

    def load_all(self) -> dict[str, dict]:
        if self._cache is not None:
            return self._cache
        manifests: dict[str, dict[str, Any]] = {}
        if not self.manifest_dir.exists() or not self.manifest_dir.is_dir():
            self._cache = manifests
            return manifests

        for path in sorted(self.manifest_dir.glob("*.y*ml")):
            payload = _load_yaml(path)
            if payload is None:
                continue
            model_id = str(payload.get("model_id") or path.stem)
            variants = payload.get("variants", [])
            if not isinstance(variants, list) or len(variants) == 0:
                # Keep behavior from main: skip structurally invalid manifests.
                continue
            manifests[model_id] = payload
        self._cache = manifests
        return manifests

    def get_manifest(self, model_id: str) -> dict:
        return dict(self.load_all().get(str(model_id).strip(), {}))

    def get_cpu_variants(self, model_id: str) -> list[dict]:
        manifest = self.get_manifest(model_id)
        variants = manifest.get("variants", [])
        if not isinstance(variants, list):
            return []
        return [v for v in variants if isinstance(v, dict) and not bool(v.get("requires_gpu", False))]

    def get_best_cpu_variant(self, model_id: str, available_ram_mb: float) -> dict | None:
        candidates = [
            v
            for v in self.get_cpu_variants(model_id)
            if float(v.get("max_ram_mb", 0.0)) <= float(available_ram_mb)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda variant: float(variant.get("cpu_tokens_per_sec", 0.0)))

    def get_export_targets(self, model_id: str) -> list[str]:
        targets = self.get_manifest(model_id).get("export_targets", [])
        return list(targets) if isinstance(targets, list) else []

    def validate_thresholds(
        self,
        model_id: str,
        latency_ms: float,
        memory_mb: float,
        accuracy_pct: float,
    ) -> dict:
        manifest = self.get_manifest(model_id)
        if not manifest:
            return {"pass": False, "error": "model_manifest_not_found", "model_id": model_id}
        thresholds = manifest.get("quality_thresholds", {}) or {}
        min_acc = float(thresholds.get("min_accuracy_pct", 0.0))
        max_latency = float(thresholds.get("max_latency_p95_ms", float("inf")))
        max_memory = float(thresholds.get("max_memory_mb", float("inf")))
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
            "thresholds": dict(thresholds),
        }


class _ManifestFactory(type):
    """Metaclass that preserves both constructor and classmethod call styles."""

    def __call__(cls, *args: Any, **kwargs: Any):  # type: ignore[override]
        if args:
            return super().__call__(*args, **kwargs)
        if kwargs.keys() == {"manifest_dir"} or ("manifest_dir" in kwargs and len(kwargs) == 1):
            return _ManifestLoader(manifest_dir=str(kwargs.get("manifest_dir", "configs/model_manifests")))
        return super().__call__(*args, **kwargs)


class ModelManifest(metaclass=_ManifestFactory):
    """
    Compatibility facade:
    - `ModelManifest(manifest_dir=...)` -> dictionary loader object for tests.
    - `ModelManifest.load(...)` / `ModelManifest.load_all(...)` -> object records.
    """

    @classmethod
    def load(cls, model_id: str, manifest_dir: str = "configs/model_manifests") -> ModelManifestRecord:
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
        payload: dict[str, Any] | None = None
        for candidate in candidate_names:
            candidate_path = manifest_root / candidate
            if candidate_path.exists():
                payload = _load_yaml(candidate_path)
                if payload is not None:
                    break
        if payload is None:
            for path in sorted(manifest_root.glob("*.y*ml")):
                maybe = _load_yaml(path)
                if maybe is None:
                    continue
                if str(maybe.get("model_id") or path.stem) == normalized:
                    payload = maybe
                    break
        if payload is None:
            raise FileNotFoundError(f"No manifest found for model_id='{normalized}' in {manifest_root}")

        model_id_actual = str(payload.get("model_id") or normalized)
        model_name = str(payload.get("model_name") or model_id_actual)
        runtime_backend = str(payload.get("runtime_backend", "llama_cpp"))
        variants_payload = payload.get("variants", []) or []
        variants: List[ManifestVariant] = []
        for item in variants_payload:
            if not isinstance(item, dict):
                continue
            variants.append(_variant_from_payload(model_id_actual, item))

        thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
        quality = payload.get("quality_thresholds")
        if isinstance(quality, dict):
            thresholds = {**thresholds, **quality}
        training = payload.get("training") if isinstance(payload.get("training"), dict) else {}
        if "adapter_tuning_allowed" in payload:
            training = {**training, "adapter_tuning_allowed": bool(payload.get("adapter_tuning_allowed"))}

        return ModelManifestRecord(
            model_id=model_id_actual,
            model_name=model_name,
            variants=variants,
            runtime_backend=runtime_backend,
            training=training,
            thresholds=thresholds,
            raw_payload=payload,
        )

    @classmethod
    def load_all(cls, manifest_dir: str = "configs/model_manifests") -> Dict[str, ModelManifestRecord]:
        manifest_root = Path(manifest_dir)
        if not manifest_root.exists():
            return {}
        loaded: Dict[str, ModelManifestRecord] = {}
        for path in sorted(manifest_root.glob("*.y*ml")):
            payload = _load_yaml(path)
            if payload is None:
                continue
            model_id = str(payload.get("model_id") or path.stem)
            try:
                loaded[model_id] = cls.load(model_id=model_id, manifest_dir=manifest_dir)
            except Exception as exc:
                LOGGER.warning("Skipping invalid manifest %s: %s", path, exc)
        return loaded
