"""
S3M CPU Training Evaluation Harness
Build-gate quality checks for CPU-trained models and adapters.

Checks:
1. Latency: p50/p95/p99 must meet manifest thresholds
2. Memory: RSS must not exceed manifest max_memory_mb
3. Accuracy: task accuracy must not regress past tolerance
4. Quantization integrity: 4-bit models must have exactly 15 unique values/layer
5. Arabic/bilingual: if model supports Arabic, test Arabic prompts
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import statistics
import time
from typing import Any

import yaml

try:
    import psutil
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None  # type: ignore[assignment]


_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")


class CPUEvaluationHarness:
    """
    Run quality gates after CPU training or quantization.

    Usage:
        harness = CPUEvaluationHarness(model_id="phi3-medium")
        report = harness.run_all(backend=my_backend, test_prompts=prompts)
        if not report.passed:
            raise RuntimeError(f"Quality gate failed: {report.violations}")
    """

    def __init__(
        self,
        model_id: str,
        manifest_dir: str = "configs/model_manifests",
        baseline_dir: str = "artifacts/eval_baselines",
        sample_size: int = 12,
        warmup_calls: int = 3,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        if int(sample_size) <= 0:
            raise ValueError("sample_size must be > 0")
        if int(warmup_calls) < 0:
            raise ValueError("warmup_calls must be >= 0")
        self.model_id = model_id.strip()
        self.manifest_dir = Path(manifest_dir)
        self.baseline_dir = Path(baseline_dir)
        self.sample_size = int(sample_size)
        self.warmup_calls = int(warmup_calls)

        self.manifest = self._load_manifest()
        self.thresholds = self._extract_thresholds(self.manifest)

    def run_all(self, backend: Any, test_prompts: list[Any], test_prompts_arabic: list[str] | None = None) -> dict:
        """Run all evaluation checks. Return comprehensive report."""
        if backend is None:
            raise ValueError("backend must not be None")
        prompts = self._validate_prompts(test_prompts)
        arabic_prompts = self._validate_arabic_prompts(test_prompts_arabic)

        latency = self.check_latency(backend=backend, prompts=prompts, thresholds=self.thresholds["latency"])
        memory = self.check_memory(backend=backend, prompts=prompts)
        accuracy = self.check_accuracy(backend=backend, prompts=prompts)

        model_obj = getattr(backend, "model", None)
        if model_obj is None:
            get_model = getattr(backend, "get_model", None)
            if callable(get_model):
                model_obj = get_model()
        quant = self.check_quantization_integrity(model=model_obj)

        arabic_required = bool(self.manifest.get("arabic_support", False))
        arabic_result: dict[str, Any]
        if arabic_required:
            arabic_result = self.check_arabic_capability(backend=backend, arabic_prompts=arabic_prompts)
        else:
            arabic_result = {
                "passed": True,
                "required": False,
                "checked_prompts": 0,
                "violations": [],
                "details": [],
            }

        checks = {
            "latency": latency,
            "memory": memory,
            "accuracy": accuracy,
            "quantization_integrity": quant,
            "arabic": arabic_result,
        }
        violations: list[str] = []
        for section, result in checks.items():
            for violation in result.get("violations", []):
                violations.append(f"{section}: {violation}")

        passed = all(bool(result.get("passed", False)) for result in checks.values())
        return {
            "model_id": self.model_id,
            "passed": passed,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "violations": violations,
            "thresholds": self.thresholds,
            "checks": checks,
        }

    def check_latency(self, backend: Any, prompts: list[Any], thresholds: dict[str, float]) -> dict:
        """
        Run N inferences, compute p50/p95/p99.
        Discard first 3 warm-up calls.
        Compare against thresholds from model manifest.
        Research benchmarks (MedLocalGPT):
          phi3-medium: ~40 tok/s on modern CPU
          7B class: ~15-45 tok/s depending on CPU
        """
        durations_ms: list[float] = []
        tps_samples: list[float] = []
        sequence = self._expand_prompts(prompts, self.sample_size + self.warmup_calls)

        for idx, prompt in enumerate(sequence):
            prompt_text = self._prompt_text(prompt)
            start = time.perf_counter()
            output = self._invoke_backend(backend, prompt_text)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if idx < self.warmup_calls:
                continue
            durations_ms.append(elapsed_ms)
            elapsed_sec = max(1e-6, elapsed_ms / 1000.0)
            token_count = max(1, len(output.split()))
            tps_samples.append(token_count / elapsed_sec)

        if not durations_ms:
            return {
                "passed": False,
                "samples": [],
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "tokens_per_second_mean": 0.0,
                "benchmark_target_tps": self._target_tps(),
                "violations": ["no post-warmup latency samples collected"],
            }

        p50 = self._percentile(durations_ms, 50.0)
        p95 = self._percentile(durations_ms, 95.0)
        p99 = self._percentile(durations_ms, 99.0)

        violations: list[str] = []
        if p50 > float(thresholds["p50_ms"]):
            violations.append(f"p50_ms exceeded ({p50:.2f} > {float(thresholds['p50_ms']):.2f})")
        if p95 > float(thresholds["p95_ms"]):
            violations.append(f"p95_ms exceeded ({p95:.2f} > {float(thresholds['p95_ms']):.2f})")
        if p99 > float(thresholds["p99_ms"]):
            violations.append(f"p99_ms exceeded ({p99:.2f} > {float(thresholds['p99_ms']):.2f})")

        return {
            "passed": not violations,
            "samples": durations_ms,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "tokens_per_second_mean": float(statistics.fmean(tps_samples)) if tps_samples else 0.0,
            "benchmark_target_tps": self._target_tps(),
            "violations": violations,
        }

    def check_memory(self, backend: Any, prompts: list[Any]) -> dict:
        """
        Measure RSS before load, after load, during inference, after unload.
        Research benchmarks:
          phi3-medium 4-bit: ~2.5 GB
          7B 4-bit: ~4.0 GB
          12B 4-bit: ~7.0 GB
        """
        rss_before = self._rss_mb()
        rss_after_load = rss_before
        rss_peak = rss_before
        load_error: str | None = None
        unload_error: str | None = None

        try:
            self._maybe_call(backend, ("load_model", "load"), self.model_id)
            rss_after_load = self._rss_mb()
            rss_peak = max(rss_peak, rss_after_load)
        except Exception as exc:
            load_error = str(exc)

        for prompt in self._expand_prompts(prompts, max(1, min(4, len(prompts)))):
            prompt_text = self._prompt_text(prompt)
            _ = self._invoke_backend(backend, prompt_text)
            rss_peak = max(rss_peak, self._rss_mb())

        rss_after_unload = self._rss_mb()
        try:
            self._maybe_call(backend, ("unload_model", "unload", "close"), self.model_id)
            rss_after_unload = self._rss_mb()
        except Exception as exc:
            unload_error = str(exc)

        max_memory = float(self.thresholds["memory"]["max_memory_mb"])
        violations: list[str] = []
        if rss_peak > max_memory:
            violations.append(f"max_memory_mb exceeded ({rss_peak:.2f} > {max_memory:.2f})")
        if load_error:
            violations.append(f"backend load failed: {load_error}")
        if unload_error:
            violations.append(f"backend unload failed: {unload_error}")

        return {
            "passed": not violations,
            "rss_before_mb": rss_before,
            "rss_after_load_mb": rss_after_load,
            "rss_peak_mb": rss_peak,
            "rss_after_unload_mb": rss_after_unload,
            "max_memory_mb": max_memory,
            "violations": violations,
        }

    def check_accuracy(self, backend: Any, prompts: list[Any]) -> dict:
        """Evaluate prompt/expected pairs and enforce regression tolerance."""
        items = self._build_accuracy_items(backend=backend, prompts=prompts)
        if not items:
            return {
                "passed": False,
                "accuracy_pct": 0.0,
                "min_accuracy_pct": float(self.thresholds["accuracy"]["min_accuracy_pct"]),
                "regression_tolerance_pct": float(self.thresholds["accuracy"]["regression_tolerance_pct"]),
                "evaluated_samples": 0,
                "matches": 0,
                "violations": ["no evaluable accuracy items"],
            }

        matches = 0
        for item in items:
            predicted = self._normalize_text(self._invoke_backend(backend, item["prompt"]))
            expected = self._normalize_text(item["expected_output"])
            if predicted == expected:
                matches += 1

        accuracy_pct = (matches / float(len(items))) * 100.0
        min_accuracy = float(self.thresholds["accuracy"]["min_accuracy_pct"])
        tolerance = float(self.thresholds["accuracy"]["regression_tolerance_pct"])
        baseline = self._baseline_accuracy_pct()

        violations: list[str] = []
        if accuracy_pct < min_accuracy:
            violations.append(f"accuracy below threshold ({accuracy_pct:.2f}% < {min_accuracy:.2f}%)")
        if baseline is not None and (baseline - accuracy_pct) > tolerance:
            violations.append(
                "accuracy regression exceeded tolerance "
                f"({baseline:.2f}% -> {accuracy_pct:.2f}%, tolerance={tolerance:.2f}%)"
            )

        return {
            "passed": not violations,
            "accuracy_pct": accuracy_pct,
            "baseline_accuracy_pct": baseline,
            "min_accuracy_pct": min_accuracy,
            "regression_tolerance_pct": tolerance,
            "evaluated_samples": len(items),
            "matches": matches,
            "violations": violations,
        }

    def check_quantization_integrity(self, model: Any) -> dict:
        """
        For 4-bit QAT models: verify each quantized layer has exactly 15
        unique weight values. From research: this invariant must hold
        throughout training and in the final exported model.
        """
        if model is None:
            return {
                "passed": False,
                "checked_layers": 0,
                "layer_unique_counts": {},
                "violations": ["model object unavailable for quantization integrity check"],
            }

        layer_weights = self._extract_layer_weights(model)
        if not layer_weights:
            return {
                "passed": False,
                "checked_layers": 0,
                "layer_unique_counts": {},
                "violations": ["no layer weights discovered in model object"],
            }

        violations: list[str] = []
        layer_unique_counts: dict[str, int] = {}
        checked_layers = 0
        for name, weight_values in layer_weights.items():
            # Tactical gate: enforce the 15-level quantized invariant before promotion.
            unique_values = {round(float(value), 6) for value in weight_values}
            unique_count = len(unique_values)
            layer_unique_counts[name] = unique_count
            checked_layers += 1
            if unique_count != 15:
                violations.append(f"{name} has {unique_count} unique values (expected 15)")

        return {
            "passed": checked_layers > 0 and not violations,
            "checked_layers": checked_layers,
            "layer_unique_counts": layer_unique_counts,
            "violations": violations,
        }

    def check_arabic_capability(self, backend: Any, arabic_prompts: list[str]) -> dict:
        """
        If model manifest indicates arabic_support=True:
        1. Run Arabic prompts
        2. Verify response is in Arabic (not garbled)
        3. Check response coherence (basic heuristic)
        """
        if not arabic_prompts:
            return {
                "passed": False,
                "required": True,
                "checked_prompts": 0,
                "violations": ["arabic_support=True but no Arabic prompts provided"],
                "details": [],
            }

        details: list[dict[str, Any]] = []
        violations: list[str] = []
        for prompt in arabic_prompts:
            response = self._invoke_backend(backend, prompt)
            has_arabic = self._arabic_ratio(response) >= 0.2
            coherent = self._is_coherent_response(response)
            row = {
                "prompt": prompt,
                "response_preview": response[:120],
                "contains_arabic": has_arabic,
                "coherent": coherent,
            }
            details.append(row)
            if not has_arabic:
                violations.append("response missing sufficient Arabic characters")
            if not coherent:
                violations.append("response failed coherence heuristic")

        return {
            "passed": not violations,
            "required": True,
            "checked_prompts": len(arabic_prompts),
            "violations": violations,
            "details": details,
        }

    def _load_manifest(self) -> dict[str, Any]:
        candidates = [
            self.manifest_dir / f"{self.model_id}.yaml",
            self.manifest_dir / f"{self.model_id}.yml",
            self.manifest_dir / f"{self.model_id.replace('-', '_')}.yaml",
            self.manifest_dir / f"{self.model_id.replace('-', '_')}.yml",
        ]
        manifest_path = next((path for path in candidates if path.exists()), None)
        if manifest_path is None:
            raise FileNotFoundError(f"Manifest not found for model_id='{self.model_id}' in {self.manifest_dir}")
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Manifest payload must be a dictionary: {manifest_path}")
        return payload

    def _extract_thresholds(self, manifest: dict[str, Any]) -> dict[str, Any]:
        quality = manifest.get("quality_thresholds", {}) if isinstance(manifest.get("quality_thresholds"), dict) else {}
        thresholds = manifest.get("thresholds", {}) if isinstance(manifest.get("thresholds"), dict) else {}
        variants = manifest.get("variants", []) if isinstance(manifest.get("variants"), list) else []

        p95 = float(quality.get("max_latency_p95_ms", thresholds.get("max_latency_p95_ms", 5000.0)))
        p50 = float(quality.get("max_latency_p50_ms", thresholds.get("max_latency_p50_ms", p95 * 0.8)))
        p99 = float(quality.get("max_latency_p99_ms", thresholds.get("max_latency_p99_ms", max(p95, p95 * 1.25))))

        variant_memory = max(
            [
                float(item.get("max_ram_mb", 0.0))
                for item in variants
                if isinstance(item, dict) and item.get("max_ram_mb") is not None
            ]
            or [0.0]
        )
        max_memory = float(quality.get("max_memory_mb", thresholds.get("max_memory_mb", max(variant_memory, 1024.0))))

        min_accuracy = float(quality.get("min_accuracy_pct", thresholds.get("min_accuracy_pct", 0.0)))
        tolerance = float(
            quality.get(
                "accuracy_regression_tolerance_pct",
                thresholds.get("accuracy_regression_tolerance_pct", 5.0),
            )
        )

        return {
            "latency": {"p50_ms": p50, "p95_ms": p95, "p99_ms": p99},
            "memory": {"max_memory_mb": max_memory},
            "accuracy": {"min_accuracy_pct": min_accuracy, "regression_tolerance_pct": tolerance},
        }

    def _target_tps(self) -> dict[str, float]:
        # Tactical baseline targets from MedLocalGPT are used to flag degraded CPU throughput.
        model_key = self.model_id.lower()
        if "phi3" in model_key:
            return {"expected_tokens_per_second": 40.0}
        if "7b" in model_key:
            return {"min_tokens_per_second": 15.0, "max_tokens_per_second": 45.0}
        return {"expected_tokens_per_second": 10.0}

    @staticmethod
    def _validate_prompts(prompts: list[Any]) -> list[Any]:
        if not isinstance(prompts, list) or not prompts:
            raise ValueError("test_prompts must be a non-empty list")
        normalized: list[Any] = []
        for row in prompts:
            if isinstance(row, str) and row.strip():
                normalized.append(row.strip())
                continue
            if isinstance(row, dict) and isinstance(row.get("prompt"), str) and row["prompt"].strip():
                normalized.append(row)
                continue
            raise ValueError("each prompt must be a non-empty string or {'prompt': ..., ...} dictionary")
        return normalized

    @staticmethod
    def _validate_arabic_prompts(prompts: list[str] | None) -> list[str]:
        if prompts is None:
            return []
        if not isinstance(prompts, list):
            raise ValueError("test_prompts_arabic must be a list of strings")
        normalized: list[str] = []
        for prompt in prompts:
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            normalized.append(prompt.strip())
        return normalized

    @staticmethod
    def _prompt_text(prompt: Any) -> str:
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, dict):
            value = prompt.get("prompt")
            if isinstance(value, str):
                return value
        raise ValueError(f"Unsupported prompt record: {type(prompt)}")

    @staticmethod
    def _extract_output_text(output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            for key in ("response", "text", "output", "generated_text", "final_answer"):
                value = output.get(key)
                if isinstance(value, str):
                    return value
            return str(output)
        for attr in ("response", "text", "output", "generated_text", "final_answer"):
            value = getattr(output, attr, None)
            if isinstance(value, str):
                return value
        return str(output)

    @classmethod
    def _invoke_backend(cls, backend: Any, prompt: str) -> str:
        for method_name in ("infer", "generate"):
            method = getattr(backend, method_name, None)
            if callable(method):
                return cls._extract_output_text(method(prompt))
        if callable(backend):
            return cls._extract_output_text(backend(prompt))
        raise AttributeError("backend must implement infer(prompt), generate(prompt), or __call__(prompt)")

    @staticmethod
    def _maybe_call(target: Any, method_names: tuple[str, ...], *args: Any) -> None:
        for name in method_names:
            method = getattr(target, name, None)
            if callable(method):
                try:
                    method(*args)
                    return
                except TypeError:
                    method()
                    return

    @staticmethod
    def _expand_prompts(prompts: list[Any], count: int) -> list[Any]:
        if not prompts:
            return []
        expanded: list[Any] = []
        index = 0
        while len(expanded) < count:
            expanded.append(prompts[index % len(prompts)])
            index += 1
        return expanded

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(float(v) for v in values)
        if len(sorted_values) == 1:
            return sorted_values[0]
        rank = (pct / 100.0) * (len(sorted_values) - 1)
        lo = int(rank)
        hi = min(lo + 1, len(sorted_values) - 1)
        frac = rank - lo
        return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac

    @staticmethod
    def _rss_mb() -> float:
        if psutil is not None:
            try:
                return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
            except Exception:
                pass
        return 0.0

    def _build_accuracy_items(self, backend: Any, prompts: list[Any]) -> list[dict[str, str]]:
        baseline = self._load_baseline_payload()
        expected_by_prompt = baseline.get("expected_by_prompt", {}) if isinstance(baseline, dict) else {}
        items: list[dict[str, str]] = []
        for row in prompts:
            prompt_text = self._prompt_text(row).strip()
            expected = None
            if isinstance(row, dict):
                expected_row = row.get("expected_output")
                if isinstance(expected_row, str) and expected_row.strip():
                    expected = expected_row.strip()
            if expected is None and isinstance(expected_by_prompt, dict):
                candidate = expected_by_prompt.get(prompt_text)
                if isinstance(candidate, str) and candidate.strip():
                    expected = candidate.strip()
            if expected is None:
                reference = self._reference_backend(backend)
                if reference is not None and reference is not backend:
                    expected = self._invoke_backend(reference, prompt_text)
            if expected is not None:
                items.append({"prompt": prompt_text, "expected_output": expected})
        return items

    def _baseline_accuracy_pct(self) -> float | None:
        payload = self._load_baseline_payload()
        raw = payload.get("accuracy_pct")
        if isinstance(raw, (int, float)):
            return float(raw)
        return None

    def _load_baseline_payload(self) -> dict[str, Any]:
        path = self.baseline_dir / f"{self.model_id}.json"
        if not path.exists():
            return {}
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
        return {}

    @staticmethod
    def _reference_backend(backend: Any) -> Any | None:
        for attr in ("fp16_backend", "reference_backend"):
            candidate = getattr(backend, attr, None)
            if candidate is not None:
                return candidate
        for method_name in ("get_fp16_backend", "get_reference_backend"):
            method = getattr(backend, method_name, None)
            if callable(method):
                candidate = method()
                if candidate is not None:
                    return candidate
        return None

    @classmethod
    def _extract_layer_weights(cls, model: Any) -> dict[str, list[float]]:
        layers: dict[str, list[float]] = {}

        quantized_layers_fn = getattr(model, "quantized_layers", None)
        if callable(quantized_layers_fn):
            for item in quantized_layers_fn():
                if isinstance(item, tuple) and len(item) == 2:
                    name, weights = item
                    flattened = cls._flatten_numeric(weights)
                    if flattened:
                        layers[str(name)] = flattened
            if layers:
                return layers

        named_parameters = getattr(model, "named_parameters", None)
        if callable(named_parameters):
            for name, parameter in named_parameters():
                if "weight" not in str(name).lower():
                    continue
                flattened = cls._flatten_numeric(parameter)
                if flattened:
                    layers[str(name)] = flattened
            if layers:
                return layers

        if isinstance(model, dict):
            for name, parameter in model.items():
                flattened = cls._flatten_numeric(parameter)
                if flattened:
                    layers[str(name)] = flattened
        return layers

    @classmethod
    def _flatten_numeric(cls, value: Any) -> list[float]:
        if value is None:
            return []
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (int, float)):
            return [float(value)]
        if isinstance(value, list):
            flattened: list[float] = []
            for item in value:
                flattened.extend(cls._flatten_numeric(item))
            return flattened
        if isinstance(value, tuple):
            flattened = []
            for item in value:
                flattened.extend(cls._flatten_numeric(item))
            return flattened
        return []

    @staticmethod
    def _normalize_text(text: str) -> str:
        compact = " ".join(str(text).strip().split())
        return compact.casefold()

    @staticmethod
    def _arabic_ratio(text: str) -> float:
        if not text:
            return 0.0
        arabic_chars = len(_ARABIC_RE.findall(text))
        return arabic_chars / float(max(1, len(text)))

    @classmethod
    def _is_coherent_response(cls, text: str) -> bool:
        if not isinstance(text, str):
            return False
        normalized = " ".join(text.strip().split())
        if len(normalized) < 8:
            return False
        if "\ufffd" in normalized:
            return False
        token_count = len(normalized.split())
        if token_count < 2:
            return False
        unique_ratio = len(set(normalized)) / float(len(normalized))
        if unique_ratio < 0.08:
            return False
        return cls._arabic_ratio(normalized) > 0.1
