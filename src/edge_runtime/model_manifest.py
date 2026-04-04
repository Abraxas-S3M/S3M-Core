"""
Per-model manifest loader for austere tactical edge deployments.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger("s3m.edge_runtime.manifest")


class ModelManifest:
    """Loads and validates per-model manifests from YAML."""

    _VALID_RUNTIME_FORMATS = {"gguf", "onnx", "openvino"}
    _REQUIRED_TOP_LEVEL = {
        "model_id",
        "provider",
        "family",
        "parameters",
        "variants",
        "adapter_tuning_allowed",
        "qat_supported",
        "export_targets",
        "primary_domain",
        "arabic_support",
        "bilingual_ar_en",
        "quality_thresholds",
    }
    _REQUIRED_VARIANT_FIELDS = {
        "tag",
        "runtime_format",
        "file",
        "size_mb",
        "max_ram_mb",
        "cpu_tokens_per_sec",
        "gpu_tokens_per_sec",
        "requires_gpu",
        "max_context",
    }
    _REQUIRED_THRESHOLD_FIELDS = {"min_accuracy_pct", "max_latency_p95_ms", "max_memory_mb"}

    def __init__(self, manifest_dir: str = "configs/model_manifests"):
        self.manifest_dir = Path(manifest_dir)
        self._cache: dict[str, dict[str, Any]] | None = None

    def load_all(self) -> dict[str, dict]:
        """Load all YAML manifests, return dict keyed by model_id."""
        if self._cache is not None:
            return self._cache

        manifests: dict[str, dict[str, Any]] = {}
        if not self.manifest_dir.exists():
            LOGGER.warning("Manifest directory not found: %s", self.manifest_dir)
            self._cache = manifests
            return manifests
        if not self.manifest_dir.is_dir():
            LOGGER.warning("Manifest path is not a directory: %s", self.manifest_dir)
            self._cache = manifests
            return manifests

        for manifest_path in sorted(self.manifest_dir.glob("*.yaml")):
            payload = self._load_yaml_file(manifest_path)
            if payload is None:
                continue

            try:
                self._validate_manifest(payload, manifest_path)
            except (TypeError, ValueError) as exc:
                LOGGER.warning("Skipping invalid manifest %s: %s", manifest_path, exc)
                continue

            model_id = payload["model_id"]
            if model_id in manifests:
                LOGGER.warning("Duplicate model_id in manifests: %s", model_id)
                continue

            manifests[model_id] = payload

        self._cache = manifests
        return manifests

    def get_manifest(self, model_id: str) -> dict:
        """Get manifest for a specific model."""
        self._require_non_empty_string("model_id", model_id)
        manifest = self.load_all().get(model_id)
        if manifest is None:
            LOGGER.warning("Requested model_id not found in manifests: %s", model_id)
            return {}
        return manifest

    def get_variant(self, model_id: str, tag: str) -> dict:
        """Get a specific variant from a model manifest."""
        self._require_non_empty_string("model_id", model_id)
        self._require_non_empty_string("tag", tag)

        manifest = self.get_manifest(model_id)
        if not manifest:
            return {}

        for variant in manifest.get("variants", []):
            if variant.get("tag") == tag:
                return variant
        return {}

    def get_cpu_variants(self, model_id: str) -> list[dict]:
        """Return only variants where requires_gpu is false."""
        manifest = self.get_manifest(model_id)
        if not manifest:
            return []
        variants = manifest.get("variants", [])
        return [variant for variant in variants if not bool(variant.get("requires_gpu", False))]

    def get_best_cpu_variant(self, model_id: str, available_ram_mb: float) -> dict | None:
        """Return highest cpu_tokens_per_sec variant that fits in RAM."""
        self._require_non_empty_string("model_id", model_id)
        self._require_finite_number("available_ram_mb", available_ram_mb, allow_zero=True)

        candidates = [
            variant
            for variant in self.get_cpu_variants(model_id)
            if float(variant["max_ram_mb"]) <= float(available_ram_mb)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda variant: float(variant["cpu_tokens_per_sec"]))

    def get_export_targets(self, model_id: str) -> list[str]:
        """Return supported export formats."""
        manifest = self.get_manifest(model_id)
        if not manifest:
            return []
        return list(manifest.get("export_targets", []))

    def validate_thresholds(
        self,
        model_id: str,
        latency_ms: float,
        memory_mb: float,
        accuracy_pct: float,
    ) -> dict:
        """Check measured values against manifest thresholds. Return pass/fail dict."""
        self._require_non_empty_string("model_id", model_id)
        self._require_finite_number("latency_ms", latency_ms, allow_zero=True)
        self._require_finite_number("memory_mb", memory_mb, allow_zero=True)
        self._require_finite_number("accuracy_pct", accuracy_pct, allow_zero=True)

        manifest = self.get_manifest(model_id)
        if not manifest:
            return {
                "pass": False,
                "error": "model_manifest_not_found",
                "model_id": model_id,
            }

        thresholds = manifest["quality_thresholds"]
        accuracy_ok = float(accuracy_pct) >= float(thresholds["min_accuracy_pct"])
        latency_ok = float(latency_ms) <= float(thresholds["max_latency_p95_ms"])
        memory_ok = float(memory_mb) <= float(thresholds["max_memory_mb"])

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

    @staticmethod
    def _load_yaml_file(path: Path) -> dict[str, Any] | None:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            LOGGER.warning("Manifest file missing: %s", path)
            return None
        except Exception as exc:
            LOGGER.warning("Unable to parse manifest file %s: %s", path, exc)
            return None

        if payload is None:
            LOGGER.warning("Manifest file is empty: %s", path)
            return None
        if not isinstance(payload, dict):
            LOGGER.warning("Manifest file must contain a mapping at top-level: %s", path)
            return None
        return payload

    @classmethod
    def _validate_manifest(cls, manifest: dict[str, Any], source_path: Path) -> None:
        missing_top_level = cls._REQUIRED_TOP_LEVEL - set(manifest.keys())
        if missing_top_level:
            raise ValueError(f"missing required top-level fields: {sorted(missing_top_level)}")

        cls._require_non_empty_string("model_id", manifest["model_id"])
        cls._require_non_empty_string("provider", manifest["provider"])
        cls._require_non_empty_string("family", manifest["family"])
        cls._require_non_empty_string("parameters", manifest["parameters"])
        cls._require_non_empty_string("primary_domain", manifest["primary_domain"])

        variants = manifest["variants"]
        if not isinstance(variants, list) or not variants:
            raise ValueError("variants must be a non-empty list")

        seen_tags: set[str] = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError("each variant must be a mapping")
            cls._validate_variant(variant)
            tag = str(variant["tag"])
            if tag in seen_tags:
                raise ValueError(f"duplicate variant tag: {tag}")
            seen_tags.add(tag)

        export_targets = manifest["export_targets"]
        if not isinstance(export_targets, list) or not export_targets:
            raise ValueError("export_targets must be a non-empty list")
        for target in export_targets:
            cls._require_non_empty_string("export_target", target)
            if str(target) not in cls._VALID_RUNTIME_FORMATS:
                raise ValueError(f"unsupported export target: {target}")

        thresholds = manifest["quality_thresholds"]
        if not isinstance(thresholds, dict):
            raise ValueError("quality_thresholds must be a mapping")
        missing_thresholds = cls._REQUIRED_THRESHOLD_FIELDS - set(thresholds.keys())
        if missing_thresholds:
            raise ValueError(f"missing quality_thresholds fields: {sorted(missing_thresholds)}")
        cls._require_finite_number("min_accuracy_pct", thresholds["min_accuracy_pct"], allow_zero=True)
        cls._require_finite_number("max_latency_p95_ms", thresholds["max_latency_p95_ms"], allow_zero=False)
        cls._require_finite_number("max_memory_mb", thresholds["max_memory_mb"], allow_zero=False)

        if not isinstance(manifest["adapter_tuning_allowed"], bool):
            raise TypeError("adapter_tuning_allowed must be a bool")
        if not isinstance(manifest["qat_supported"], bool):
            raise TypeError("qat_supported must be a bool")
        if not isinstance(manifest["arabic_support"], bool):
            raise TypeError("arabic_support must be a bool")
        if not isinstance(manifest["bilingual_ar_en"], bool):
            raise TypeError("bilingual_ar_en must be a bool")

        if not source_path.name.endswith(".yaml"):
            raise ValueError("manifest source must be .yaml")

    @classmethod
    def _validate_variant(cls, variant: dict[str, Any]) -> None:
        missing_variant_fields = cls._REQUIRED_VARIANT_FIELDS - set(variant.keys())
        if missing_variant_fields:
            raise ValueError(f"missing variant fields: {sorted(missing_variant_fields)}")

        cls._require_non_empty_string("tag", variant["tag"])
        cls._require_non_empty_string("runtime_format", variant["runtime_format"])
        cls._require_non_empty_string("file", variant["file"])
        cls._require_finite_number("size_mb", variant["size_mb"], allow_zero=False)
        cls._require_finite_number("max_ram_mb", variant["max_ram_mb"], allow_zero=False)
        cls._require_finite_number("cpu_tokens_per_sec", variant["cpu_tokens_per_sec"], allow_zero=True)
        cls._require_finite_number("gpu_tokens_per_sec", variant["gpu_tokens_per_sec"], allow_zero=True)
        cls._require_finite_number("max_context", variant["max_context"], allow_zero=False)

        if variant["runtime_format"] not in cls._VALID_RUNTIME_FORMATS:
            raise ValueError(f"unsupported runtime_format: {variant['runtime_format']}")
        if not isinstance(variant["requires_gpu"], bool):
            raise TypeError("requires_gpu must be a bool")

    @staticmethod
    def _require_non_empty_string(name: str, value: Any) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    @staticmethod
    def _require_finite_number(name: str, value: Any, *, allow_zero: bool) -> None:
        if not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be numeric")
        value_float = float(value)
        if not math.isfinite(value_float):
            raise ValueError(f"{name} must be finite")
        if allow_zero:
            if value_float < 0:
                raise ValueError(f"{name} must be non-negative")
        elif value_float <= 0:
            raise ValueError(f"{name} must be positive")
