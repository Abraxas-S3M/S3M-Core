"""
S3M Speculative Thermal-Aware Inference Scheduler (STAIS)
ORIGINAL ALGORITHM — Proactive thermal management for CPU inference

Problem: Reactive thermal management (wait for overheat, then throttle)
causes latency spikes during critical tactical operations.

Solution: Predict thermal trajectory from workload history, preemptively
adjust quantization level, thread count, and batch configuration to stay
below thermal limits. The CPU never throttles because we stay ahead of it.

Thermal model:
  T(t+dt) = T(t) + (P_compute * dt / C_thermal) - (T(t) - T_ambient) * dt / R_thermal

  Where:
    P_compute = f(num_threads, precision_level, tokens_per_second)
    C_thermal = thermal capacitance (calibrated at boot)
    R_thermal = thermal resistance to ambient (calibrated at boot)
    T_ambient = measured ambient temperature

  We calibrate C_thermal and R_thermal during the boot-time hardware profiling
  by running a short thermal stress test and measuring the slope.

  Given the current request queue (next N inference requests), we can predict
  what T will be after each request completes, and preemptively adjust
  parameters to keep T < T_throttle - margin.

Adjustment knobs (in priority order):
  1. Thread count reduction (e.g., 16 → 12 threads) — least quality impact
  2. Cascade level demotion (INT8 → INT4) — moderate quality impact
  3. Request deferral (delay non-critical requests) — latency impact
  4. Batch size reduction — throughput impact
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field, replace
import logging
import math
from pathlib import Path
import time
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("s3m.edge_runtime.thermal_scheduler")

CASCADE_LEVELS: Tuple[str, ...] = ("int8", "int4", "ternary")


@dataclass
class ThermalModel:
    """Calibrated thermal model for this specific CPU."""

    thermal_capacitance: float  # J/degC — calibrated at boot
    thermal_resistance: float  # degC/W — calibrated at boot
    ambient_temp_c: float  # measured ambient
    throttle_temp_c: float  # CPU throttle threshold (typically 95-100C)
    target_temp_c: float  # our target max (throttle - margin)
    margin_c: float = 10.0  # safety margin below throttle
    # Power model coefficients (kept conservative for mission continuity)
    power_per_thread_w: float = 3.0
    power_per_int8_tok_w: float = 0.5
    power_per_int4_tok_w: float = 0.3
    power_per_ternary_tok_w: float = 0.1


@dataclass
class InferenceRequest:
    """A queued inference request with priority."""

    request_id: str
    prompt_tokens: int
    max_output_tokens: int
    priority: int = 0  # 0=normal, 1=tactical, 2=critical
    min_cascade_level: str = "ternary"  # lowest acceptable quality
    timestamp: float = field(default_factory=time.time)


@dataclass
class ThermalPrediction:
    """Predicted thermal state after processing a request."""

    request_id: str
    predicted_temp_c: float
    predicted_duration_s: float
    recommended_threads: int
    recommended_cascade_level: str
    should_defer: bool
    confidence: float  # prediction confidence based on calibration quality


class ThermalInferenceScheduler:
    """
    Proactively manages inference to prevent thermal throttling.

    Boot sequence:
    1. Read current temperature from hardware profiler
    2. Run 10-second calibration burst (matrix multiply at full threads)
    3. Measure temperature rise → compute thermal_capacitance
    4. Wait 10 seconds idle, measure cooldown → compute thermal_resistance
    5. Set target_temp = throttle_temp - margin

    Runtime:
    1. Receive inference request
    2. Predict thermal impact using calibrated model
    3. If predicted to exceed target: adjust parameters preemptively
    4. Execute inference with adjusted parameters
    5. Update thermal model with actual observations (online calibration)
    """

    def __init__(self, profile, thermal_model: Optional[ThermalModel] = None):
        self.profile = profile
        self.model = thermal_model
        self._temp_history: Deque[Tuple[float, float]] = collections.deque(maxlen=1000)
        self._prediction_errors: Deque[float] = collections.deque(maxlen=100)
        self._prediction_bias: Deque[float] = collections.deque(maxlen=100)
        self._request_predictions: Dict[str, float] = {}
        self._calibration_quality: float = 0.25
        self._sensor_paths: List[Path] = self._discover_thermal_sensors()
        self._enabled: bool = bool(thermal_model is not None or self._sensor_paths)
        if not self._enabled:
            logger.warning("STAIS disabled: no thermal sensor discovered under /sys/class/thermal/thermal_zone*/temp.")

    def calibrate(self, duration_s: float = 10.0) -> ThermalModel:
        """
        Run thermal calibration at boot time.
        1. Record baseline temperature
        2. Run CPU stress for duration_s seconds
        3. Record peak temperature
        4. Idle for duration_s seconds
        5. Record cooldown temperature
        6. Compute C_thermal and R_thermal
        Returns calibrated ThermalModel.
        """

        if not math.isfinite(duration_s) or duration_s <= 0.0:
            raise ValueError("duration_s must be a finite positive float")
        if self._is_inference_active():
            raise RuntimeError("Calibration cannot run while active inference is in progress.")

        baseline = self._read_current_temperature()
        if baseline is None:
            self._enabled = False
            fallback = self._fallback_model()
            self.model = fallback
            self._calibration_quality = 0.0
            logger.warning("STAIS calibration skipped: no readable thermal sensor.")
            return fallback

        self._enabled = True
        self._run_stress_test(duration_s)
        peak = self._read_current_temperature()
        if peak is None:
            peak = baseline

        time.sleep(duration_s)
        cooldown = self._read_current_temperature()
        if cooldown is None:
            cooldown = peak

        full_threads = self._default_threads()
        stress_power_w = self._estimate_power(
            threads=full_threads,
            cascade_level="int8",
            tokens=max(32, int(full_threads * 8)),
        )
        temp_rise = max(0.1, peak - baseline)
        thermal_capacitance = max(25.0, (stress_power_w * duration_s) / temp_rise)

        ambient = self._ambient_reference(baseline_c=baseline)
        thermal_resistance = self._estimate_thermal_resistance(
            peak_temp_c=peak,
            cooldown_temp_c=cooldown,
            ambient_temp_c=ambient,
            duration_s=duration_s,
            thermal_capacitance=thermal_capacitance,
        )
        throttle = self._throttle_reference()
        margin = 10.0
        target = throttle - margin
        model = ThermalModel(
            thermal_capacitance=thermal_capacitance,
            thermal_resistance=thermal_resistance,
            ambient_temp_c=ambient,
            throttle_temp_c=throttle,
            target_temp_c=target,
            margin_c=margin,
        )
        self.model = model

        rise_score = min(1.0, max(0.0, temp_rise / 8.0))
        cooldown_score = 1.0 if cooldown < peak else 0.4
        self._calibration_quality = max(0.2, min(0.95, 0.2 + 0.55 * rise_score + 0.25 * cooldown_score))
        return model

    def schedule_request(self, request: InferenceRequest, current_temp_c: float) -> ThermalPrediction:
        """
        Predict thermal impact and recommend parameters.

        1. Estimate compute power for request at current settings
        2. Predict temperature trajectory over request duration
        3. If predicted peak > target_temp:
           a. Try reducing threads (cheapest adjustment)
           b. Try demoting cascade level
           c. If still too hot and priority < 2: defer request
        4. Return recommendation

        The prediction uses the simple thermal RC model:
        T(t+dt) = T_amb + (T(t) - T_amb) * exp(-dt/RC) + P*R*(1 - exp(-dt/RC))
        """

        self._validate_request(request)
        if not math.isfinite(current_temp_c):
            raise ValueError("current_temp_c must be finite")

        if not self._enabled or self.model is None:
            fallback_prediction = ThermalPrediction(
                request_id=request.request_id,
                predicted_temp_c=float(current_temp_c),
                predicted_duration_s=self._estimate_duration_s(request, self._default_threads(), "int8"),
                recommended_threads=self._default_threads(),
                recommended_cascade_level="int8",
                should_defer=False,
                confidence=0.0,
            )
            self._request_predictions[request.request_id] = fallback_prediction.predicted_temp_c
            return fallback_prediction

        config = self._find_optimal_config(request=request, current_temp=float(current_temp_c), max_temp=self.model.target_temp_c)
        confidence = self._prediction_confidence()
        prediction = ThermalPrediction(
            request_id=request.request_id,
            predicted_temp_c=float(config["predicted_temp_c"]),
            predicted_duration_s=float(config["duration_s"]),
            recommended_threads=int(config["threads"]),
            recommended_cascade_level=str(config["cascade_level"]),
            should_defer=bool(config["should_defer"]),
            confidence=confidence,
        )
        self._request_predictions[request.request_id] = prediction.predicted_temp_c
        return prediction

    def record_observation(self, request_id: str, actual_temp_c: float, actual_duration_s: float) -> None:
        """
        Record actual thermal result after inference completes.
        Compare to prediction, update running calibration error.
        If error consistently biased: adjust thermal model online.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not math.isfinite(actual_temp_c):
            raise ValueError("actual_temp_c must be finite")
        if not math.isfinite(actual_duration_s) or actual_duration_s <= 0.0:
            raise ValueError("actual_duration_s must be a finite positive float")

        self._temp_history.append((time.time(), float(actual_temp_c)))
        predicted = self._request_predictions.pop(request_id, None)
        if predicted is None:
            return

        error = float(actual_temp_c - predicted)
        self._prediction_bias.append(error)
        self._prediction_errors.append(abs(error))

        if self.model is None:
            return
        if len(self._prediction_bias) < 5:
            return

        mean_bias = sum(self._prediction_bias) / len(self._prediction_bias)
        if abs(mean_bias) < 0.6:
            return

        old = self.model
        if mean_bias > 0.0:
            c_factor = 1.0 - min(0.12, abs(mean_bias) * 0.02)
            r_factor = 1.0 + min(0.12, abs(mean_bias) * 0.02)
        else:
            c_factor = 1.0 + min(0.08, abs(mean_bias) * 0.015)
            r_factor = 1.0 - min(0.08, abs(mean_bias) * 0.015)

        updated = replace(
            old,
            thermal_capacitance=max(20.0, old.thermal_capacitance * c_factor),
            thermal_resistance=max(0.2, old.thermal_resistance * r_factor),
        )
        # Tactical runtime uses single-writer replacement so readers never block.
        self.model = updated
        self._calibration_quality = max(0.1, self._calibration_quality * 0.995)

    def _predict_temperature(self, current_temp: float, power_w: float, duration_s: float) -> float:
        """Apply thermal RC model to predict future temperature."""

        if self.model is None:
            return float(current_temp)
        if duration_s <= 0.0:
            return float(current_temp)

        thermal_time_constant = max(1e-6, self.model.thermal_capacitance * self.model.thermal_resistance)
        decay = math.exp(-duration_s / thermal_time_constant)
        ambient = self.model.ambient_temp_c
        return ambient + (current_temp - ambient) * decay + power_w * self.model.thermal_resistance * (1.0 - decay)

    def _estimate_power(self, threads: int, cascade_level: str, tokens: int) -> float:
        """Estimate total power draw for given inference configuration."""

        if self.model is not None:
            m = self.model
            per_thread = m.power_per_thread_w
            int8_k = m.power_per_int8_tok_w
            int4_k = m.power_per_int4_tok_w
            ternary_k = m.power_per_ternary_tok_w
        else:
            per_thread = 3.0
            int8_k = 0.5
            int4_k = 0.3
            ternary_k = 0.1

        level = self._normalize_cascade_level(cascade_level)
        tok_rate = max(1, int(tokens))
        dynamic_coeff = {"int8": int8_k, "int4": int4_k, "ternary": ternary_k}[level]
        conservative_thread = float(max(1, threads)) * per_thread * 1.15
        conservative_dynamic = dynamic_coeff * float(tok_rate) * 1.2
        return conservative_thread + conservative_dynamic

    def _find_optimal_config(self, request: InferenceRequest, current_temp: float, max_temp: float) -> dict:
        """
        Search over (threads, cascade_level) space to find
        the highest quality configuration that stays below max_temp.

        Search order (prefer quality):
        1. Full threads, current cascade level
        2. Reduced threads (75%), current cascade level
        3. Reduced threads (50%), current cascade level
        4. Full threads, one level lower cascade
        5. Reduced threads (75%), one level lower cascade
        ...
        Return first configuration that fits thermal budget.
        """

        threads_full = self._default_threads()
        thread_candidates: List[int] = []
        for candidate in (threads_full, int(math.ceil(threads_full * 0.75)), int(math.ceil(threads_full * 0.5))):
            candidate = max(1, min(threads_full, candidate))
            if candidate not in thread_candidates:
                thread_candidates.append(candidate)

        cascade_candidates = self._allowed_cascades(request.min_cascade_level)
        total_tokens = max(1, request.prompt_tokens + request.max_output_tokens)
        best = {
            "threads": thread_candidates[-1],
            "cascade_level": cascade_candidates[-1],
            "duration_s": self._estimate_duration_s(request, thread_candidates[-1], cascade_candidates[-1]),
            "predicted_temp_c": float("inf"),
            "should_defer": False,
        }

        for cascade in cascade_candidates:
            for threads in thread_candidates:
                duration_s = self._estimate_duration_s(request, threads, cascade)
                token_rate = max(1, int(total_tokens / max(duration_s, 1e-3)))
                power_w = self._estimate_power(threads=threads, cascade_level=cascade, tokens=token_rate)
                predicted_temp_c = self._predict_temperature(current_temp=current_temp, power_w=power_w, duration_s=duration_s)
                candidate = {
                    "threads": threads,
                    "cascade_level": cascade,
                    "duration_s": duration_s,
                    "predicted_temp_c": predicted_temp_c,
                    "should_defer": False,
                }
                if predicted_temp_c <= max_temp:
                    return candidate
                if predicted_temp_c < best["predicted_temp_c"]:
                    best = candidate

        if request.priority < 2:
            best["should_defer"] = True
        return best

    def get_thermal_status(self) -> dict:
        """Current thermal state, prediction accuracy, calibration quality."""

        current_temp = self._read_current_temperature()
        mae = (sum(self._prediction_errors) / len(self._prediction_errors)) if self._prediction_errors else None
        return {
            "enabled": self._enabled,
            "sensor_available": bool(self._sensor_paths),
            "current_temp_c": current_temp,
            "model": None
            if self.model is None
            else {
                "thermal_capacitance": self.model.thermal_capacitance,
                "thermal_resistance": self.model.thermal_resistance,
                "ambient_temp_c": self.model.ambient_temp_c,
                "throttle_temp_c": self.model.throttle_temp_c,
                "target_temp_c": self.model.target_temp_c,
                "margin_c": self.model.margin_c,
            },
            "prediction_confidence": self._prediction_confidence(),
            "mean_abs_error_c": mae,
            "observations": len(self._temp_history),
        }

    def _discover_thermal_sensors(self) -> List[Path]:
        thermal_root = Path("/sys/class/thermal")
        if not thermal_root.exists():
            return []
        return sorted(thermal_root.glob("thermal_zone*/temp"))

    def _read_current_temperature(self) -> Optional[float]:
        if not self._sensor_paths:
            return None
        values: List[float] = []
        for sensor in self._sensor_paths:
            try:
                raw = sensor.read_text(encoding="utf-8", errors="ignore").strip()
                if not raw:
                    continue
                reading = float(raw)
                if reading > 1000.0:
                    reading = reading / 1000.0
                if math.isfinite(reading):
                    values.append(reading)
            except Exception:
                continue
        if not values:
            return None
        # Conservative tactical posture uses hottest zone to prevent surprise throttling.
        return max(values)

    def _run_stress_test(self, duration_s: float) -> None:
        run_stress = getattr(self.profile, "run_thermal_stress", None)
        if callable(run_stress):
            try:
                run_stress(duration_s)
                return
            except Exception:
                logger.exception("Custom run_thermal_stress callback failed; using built-in fallback.")
        deadline = time.time() + duration_s
        value = 1.0001
        while time.time() < deadline:
            value = math.sqrt(value) * 1.00001
            if value < 1.0:
                value = 1.0001

    def _is_inference_active(self) -> bool:
        for attr in ("inference_active", "active_inference"):
            if bool(getattr(self.profile, attr, False)):
                return True
        fn = getattr(self.profile, "is_inference_active", None)
        if callable(fn):
            try:
                return bool(fn())
            except Exception:
                return True
        return False

    def _default_threads(self) -> int:
        return max(1, int(getattr(self.profile, "cpu_cores", 4)))

    def _ambient_reference(self, baseline_c: float) -> float:
        ambient = getattr(self.profile, "ambient_temp_c", None)
        if isinstance(ambient, (int, float)) and math.isfinite(float(ambient)):
            return float(ambient)
        return max(10.0, min(float(baseline_c), float(baseline_c) - 5.0 if baseline_c > 20.0 else baseline_c))

    def _throttle_reference(self) -> float:
        throttle = getattr(self.profile, "throttle_temp_c", None)
        if isinstance(throttle, (int, float)) and math.isfinite(float(throttle)):
            return float(throttle)
        return 95.0

    def _estimate_thermal_resistance(
        self,
        peak_temp_c: float,
        cooldown_temp_c: float,
        ambient_temp_c: float,
        duration_s: float,
        thermal_capacitance: float,
    ) -> float:
        numerator = cooldown_temp_c - ambient_temp_c
        denominator = peak_temp_c - ambient_temp_c
        if denominator <= 0.0 or numerator <= 0.0:
            return 1.2
        ratio = max(1e-3, min(0.999, numerator / denominator))
        rc = -duration_s / math.log(ratio)
        return max(0.2, rc / max(1e-6, thermal_capacitance))

    def _prediction_confidence(self) -> float:
        if not self._enabled or self.model is None:
            return 0.0
        quality = max(0.05, min(1.0, self._calibration_quality))
        if not self._prediction_errors:
            return round(min(0.99, quality), 3)
        mae = sum(self._prediction_errors) / len(self._prediction_errors)
        error_factor = max(0.1, 1.0 - (mae / 20.0))
        return round(max(0.05, min(0.99, quality * error_factor)), 3)

    def _estimate_duration_s(self, request: InferenceRequest, threads: int, cascade_level: str) -> float:
        total_tokens = max(1, int(request.prompt_tokens + request.max_output_tokens))
        level = self._normalize_cascade_level(cascade_level)
        per_thread_tps = {"int8": 5.0, "int4": 6.5, "ternary": 8.0}[level]
        effective_tps = max(1.0, per_thread_tps * max(1, threads) * 0.9)
        return max(0.05, total_tokens / effective_tps)

    def _allowed_cascades(self, min_cascade_level: str) -> List[str]:
        normalized = self._normalize_cascade_level(min_cascade_level)
        min_index = CASCADE_LEVELS.index(normalized)
        return list(CASCADE_LEVELS[: min_index + 1])

    def _normalize_cascade_level(self, level: str) -> str:
        if not isinstance(level, str):
            raise TypeError("cascade level must be a string")
        lowered = level.strip().lower()
        alias = {
            "8bit": "int8",
            "int8": "int8",
            "q8": "int8",
            "4bit": "int4",
            "int4": "int4",
            "q4": "int4",
            "ternary": "ternary",
            "int2": "ternary",
        }
        normalized = alias.get(lowered)
        if normalized is None:
            raise ValueError(f"Unsupported cascade level: {level}")
        return normalized

    def _validate_request(self, request: InferenceRequest) -> None:
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            raise ValueError("request.request_id must be a non-empty string")
        if int(request.prompt_tokens) < 0:
            raise ValueError("request.prompt_tokens must be >= 0")
        if int(request.max_output_tokens) <= 0:
            raise ValueError("request.max_output_tokens must be > 0")
        if int(request.priority) not in (0, 1, 2):
            raise ValueError("request.priority must be 0, 1, or 2")
        self._normalize_cascade_level(request.min_cascade_level)

    def _fallback_model(self) -> ThermalModel:
        throttle = self._throttle_reference()
        margin = 10.0
        ambient = float(getattr(self.profile, "ambient_temp_c", 25.0))
        if not math.isfinite(ambient):
            ambient = 25.0
        return ThermalModel(
            thermal_capacitance=220.0,
            thermal_resistance=1.2,
            ambient_temp_c=ambient,
            throttle_temp_c=throttle,
            target_temp_c=throttle - margin,
            margin_c=margin,
        )
