"""RUL estimator with ML adapters and rule fallback for air-gapped deployments."""

from __future__ import annotations

import csv
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from services.maintenance.models import Asset, AssetType, RULPrediction, SensorTelemetry


class RULEstimator:
    """Estimate remaining useful life for tactical platform sustainment."""

    def __init__(self, model_backend: str = "auto"):
        self.model_backend = model_backend
        self.backend = "rules"
        self.model = None
        self.model_path: Optional[str] = None
        self._torch = None
        self._joblib = None
        self._init_backend()

    def _init_backend(self) -> None:
        lstm_path = Path("models/maintenance/rul_lstm.pt")
        gbm_path = Path("models/maintenance/rul_gbm.pkl")
        rf_path = Path("models/maintenance/rul_rf.pkl")

        if self.model_backend not in {"auto", "lstm", "gbm", "rf", "rules"}:
            self.model_backend = "auto"

        if self.model_backend in {"auto", "lstm"}:
            try:
                import torch

                if lstm_path.exists():
                    self._torch = torch
                    self.model = torch.jit.load(str(lstm_path), map_location="cpu")
                    self.model.eval()
                    self.backend = "lstm"
                    self.model_path = str(lstm_path)
                    return
            except Exception:
                pass

        if self.model_backend in {"auto", "gbm", "rf"}:
            try:
                import sklearn  # noqa: F401

                try:
                    import joblib

                    self._joblib = joblib
                except Exception:
                    self._joblib = None

                if gbm_path.exists() and self.model_backend in {"auto", "gbm"}:
                    self.model = self._load_pickle(gbm_path)
                    self.backend = "gbm"
                    self.model_path = str(gbm_path)
                    return
                if rf_path.exists() and self.model_backend in {"auto", "rf"}:
                    self.model = self._load_pickle(rf_path)
                    self.backend = "rf"
                    self.model_path = str(rf_path)
                    return
            except Exception:
                pass

        self.backend = "rules"
        self.model = None
        self.model_path = None

    def _load_pickle(self, path: Path) -> Any:
        if self._joblib is not None:
            return self._joblib.load(path)
        with path.open("rb") as handle:
            return pickle.load(handle)

    def _aggregate_features(self, telemetry_history: List[SensorTelemetry]) -> Tuple[np.ndarray, Dict[str, float]]:
        if not telemetry_history:
            vec = np.zeros(18, dtype=float)
            fmap = {f"f{i}": float(vec[i]) for i in range(len(vec))}
            return vec, fmap

        keys = ["temperature_c", "vibration_g", "pressure_psi", "oil_temp_c", "rpm", "fuel_flow_rate"]
        series = {key: [] for key in keys}
        for point in telemetry_history[-30:]:
            for key in keys:
                raw = point.readings.get(key)
                series[key].append(float(raw) if isinstance(raw, (int, float)) else 0.0)

        features: List[float] = []
        fmap: Dict[str, float] = {}
        for key in keys:
            arr = np.array(series[key], dtype=float)
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            slope = float((arr[-1] - arr[0]) / max(1, len(arr) - 1))
            features.extend([mean, std, slope])
            fmap[f"{key}_mean"] = mean
            fmap[f"{key}_std"] = std
            fmap[f"{key}_slope"] = slope
        return np.array(features, dtype=float), fmap

    def _max_life_for_asset(self, asset_type: AssetType) -> float:
        if asset_type in {
            AssetType.AIRCRAFT,
            AssetType.FIGHTER_JET,
            AssetType.HELICOPTER,
            AssetType.TRANSPORT_AIRCRAFT,
            AssetType.UAV,
        }:
            return 5000.0
        if asset_type in {AssetType.GROUND_VEHICLE, AssetType.APC, AssetType.TANK, AssetType.TRUCK}:
            return 8000.0
        if asset_type in {AssetType.NAVAL_VESSEL, AssetType.PATROL_BOAT, AssetType.FRIGATE}:
            return 10000.0
        return 6000.0

    def _rules_predict(
        self, telemetry_history: List[SensorTelemetry], asset: Asset, feature_map: Dict[str, float]
    ) -> Tuple[float, float, str]:
        latest = telemetry_history[-1].readings if telemetry_history else {}
        temperature = float(latest.get("temperature_c", 0.0))
        vibration = float(latest.get("vibration_g", 0.0))
        pressure = float(latest.get("pressure_psi", 0.0))
        baseline_pressure = (
            float(telemetry_history[0].readings.get("pressure_psi", pressure or 1.0))
            if telemetry_history
            else max(pressure, 1.0)
        )
        pressure_drop = (baseline_pressure - pressure) / max(1e-6, baseline_pressure)

        max_life = self._max_life_for_asset(asset.asset_type)
        linear_rul = max(0.0, max_life - float(asset.operating_hours))
        rul = linear_rul
        confidence = 0.62
        failure_mode = "normal_wear"

        # Tactical threshold rules aligned to NASA CMAPSS style degradation signals.
        if temperature > 500:
            rul = min(rul, 40.0)
            confidence = 0.93
            failure_mode = "thermal_overstress"
        if vibration > 5:
            rul = min(rul, 90.0)
            confidence = max(confidence, 0.88)
            failure_mode = "mechanical_vibration"
        if pressure_drop > 0.20:
            rul = min(rul, 180.0)
            confidence = max(confidence, 0.8)
            failure_mode = "pressure_leak"

        feature_map["pressure_drop_pct"] = round(pressure_drop * 100.0, 3)
        return float(max(0.0, rul)), float(confidence), failure_mode

    def _risk_level(self, rul_hours: float) -> str:
        if rul_hours < 50:
            return "critical"
        if rul_hours < 200:
            return "high"
        if rul_hours < 500:
            return "medium"
        return "low"

    def _failure_mode_from_features(self, feature_map: Dict[str, float]) -> str:
        temp = feature_map.get("temperature_c_mean", 0.0)
        vib = feature_map.get("vibration_g_mean", 0.0)
        pressure_slope = feature_map.get("pressure_psi_slope", 0.0)
        if temp > 500 and vib > 5:
            return "bearing_degradation"
        if temp > 500:
            return "combustion_issue"
        if pressure_slope < -1.0:
            return "seal_leak"
        if vib > 4:
            return "blade_erosion"
        return "gradual_wear"

    def _recommendation(self, asset: Asset, failure_mode: str, rul: float) -> str:
        action = "inspect within 72h"
        if rul < 50:
            action = "ground immediately and execute emergency maintenance"
        elif rul < 200:
            action = "schedule urgent predictive maintenance"
        elif rul < 500:
            action = "plan preventive maintenance in current cycle"

        prompt = f"Asset {asset.designation} shows {failure_mode} with RUL {rul:.1f}h. Recommend: {action}."
        try:
            from src.llm_core.inference import S3MInference

            text = S3MInference().generate(prompt, max_tokens=120)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass
        return prompt

    def predict(self, telemetry_history: List[SensorTelemetry], asset: Asset) -> RULPrediction:
        features, fmap = self._aggregate_features(telemetry_history)
        rul = 0.0
        confidence = 0.6
        failure_mode = self._failure_mode_from_features(fmap)
        model_used = self.backend

        if self.backend == "lstm" and self.model is not None and telemetry_history:
            try:
                seq = [point.to_feature_vector() for point in telemetry_history[-20:]]
                max_len = max(len(row) for row in seq)
                seq = [row + [0.0] * (max_len - len(row)) for row in seq]
                tensor = self._torch.tensor([seq], dtype=self._torch.float32)
                with self._torch.no_grad():
                    output = self.model(tensor)
                rul = float(output.flatten()[0].item())
                confidence = 0.84
            except Exception:
                rul, confidence, failure_mode = self._rules_predict(telemetry_history, asset, fmap)
                model_used = "rules"
        elif self.backend in {"gbm", "rf"} and self.model is not None:
            try:
                if hasattr(self.model, "predict"):
                    needed = int(getattr(self.model, "n_features_in_", len(features)))
                    x = np.array(features[:needed], dtype=float)
                    if len(x) < needed:
                        x = np.pad(x, (0, needed - len(x)), mode="constant")
                    rul = float(self.model.predict([x])[0])
                    confidence = 0.8
                else:
                    rul, confidence, failure_mode = self._rules_predict(telemetry_history, asset, fmap)
                    model_used = "rules"
            except Exception:
                rul, confidence, failure_mode = self._rules_predict(telemetry_history, asset, fmap)
                model_used = "rules"
        else:
            rul, confidence, failure_mode = self._rules_predict(telemetry_history, asset, fmap)
            model_used = "rules"

        rul = max(0.0, float(rul))
        risk = self._risk_level(rul)
        recommendation = self._recommendation(asset=asset, failure_mode=failure_mode, rul=rul)
        return RULPrediction(
            prediction_id=f"rul-{uuid4().hex[:10]}",
            asset_id=asset.asset_id,
            timestamp=datetime.now(timezone.utc),
            rul_hours=rul,
            confidence=confidence,
            model_used=model_used,
            risk_level=risk,
            failure_mode=failure_mode,
            sensor_features=fmap,
            recommendation=recommendation,
        )

    def predict_batch(self, assets: List[tuple]) -> List[RULPrediction]:
        out: List[RULPrediction] = []
        for asset, telemetry_history in assets:
            out.append(self.predict(telemetry_history=telemetry_history, asset=asset))
        return out

    def train(self, dataset_path: str, model_type: str = "gbm") -> dict:
        try:
            from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            from sklearn.model_selection import train_test_split
        except Exception:
            return {"error": "No ML library available for training"}

        path = Path(dataset_path)
        if not path.exists():
            return {"error": f"Dataset not found: {dataset_path}"}

        rows: List[Dict[str, float]] = []
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(row)
        if not rows:
            return {"error": "Dataset is empty"}

        feature_cols = [col for col in rows[0].keys() if col.startswith("sensor_")]
        if "cycle" in rows[0]:
            feature_cols = ["cycle"] + feature_cols
        if "RUL" not in rows[0]:
            return {"error": "Dataset must include RUL column"}

        x = np.array([[float(row.get(col, 0.0)) for col in feature_cols] for row in rows], dtype=float)
        y = np.array([float(row.get("RUL", 0.0)) for row in rows], dtype=float)

        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)
        if model_type.lower() == "rf":
            model = RandomForestRegressor(n_estimators=120, random_state=42)
            model_path = Path("models/maintenance/rul_rf.pkl")
            backend = "rf"
        else:
            model = GradientBoostingRegressor(random_state=42)
            model_path = Path("models/maintenance/rul_gbm.pkl")
            backend = "gbm"

        model.fit(x_train, y_train)
        pred = model.predict(x_test)
        mae = float(mean_absolute_error(y_test, pred))
        rmse = float(math.sqrt(mean_squared_error(y_test, pred)))
        r2 = float(r2_score(y_test, pred))

        model_path.parent.mkdir(parents=True, exist_ok=True)
        with model_path.open("wb") as handle:
            pickle.dump(model, handle)

        self.model = model
        self.backend = backend
        self.model_path = str(model_path)
        return {
            "model_type": backend,
            "model_path": str(model_path),
            "metrics": {"MAE": mae, "RMSE": rmse, "R2": r2},
            "samples": int(len(rows)),
            "features": feature_cols,
        }

    def get_model_info(self) -> dict:
        return {
            "backend": self.backend,
            "configured_backend": self.model_backend,
            "model_loaded": self.model is not None,
            "model_path": self.model_path,
        }
