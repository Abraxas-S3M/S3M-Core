"""Fleet reliability analysis for sustainment predictions.

This module trains Kaplan-Meier survival models from local maintenance history
so sustainment dashboards can prioritize at-risk military assets while fully
offline in tactical deployments.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.maintenance.models import Asset, MaintenanceRecord

try:  # pragma: no cover - exercised when optional dependency is present
    from lifelines import KaplanMeierFitter
except Exception:  # pragma: no cover - fallback path covered in tests
    KaplanMeierFitter = None  # type: ignore[assignment]


class OperationalStore:
    """Read fleet and maintenance history from the local maintenance service."""

    def get_assets(self) -> list[Asset]:
        try:
            from src.api.maintenance_routes import _maintenance

            return list(_maintenance.asset_registry.assets.values())
        except Exception:
            return []

    def get_maintenance_history(self, asset_id: str) -> list[MaintenanceRecord]:
        if not isinstance(asset_id, str) or not asset_id.strip():
            return []
        try:
            from src.api.maintenance_routes import _maintenance

            return _maintenance.asset_registry.get_maintenance_history(asset_id)
        except Exception:
            return []


class ReliabilityAnalyzer:
    """Estimate remaining useful life using Kaplan-Meier survival analysis."""

    _DEFAULT_MAX_LIFE_HOURS: dict[str, float] = {
        "AIRCRAFT": 5000.0,
        "FIGHTER_JET": 5000.0,
        "HELICOPTER": 5000.0,
        "TRANSPORT_AIRCRAFT": 5000.0,
        "UAV": 5000.0,
        "GROUND_VEHICLE": 8000.0,
        "APC": 8000.0,
        "TANK": 8000.0,
        "TRUCK": 8000.0,
        "NAVAL_VESSEL": 10000.0,
        "PATROL_BOAT": 10000.0,
        "FRIGATE": 10000.0,
    }

    def __init__(self, operational_store: OperationalStore | None = None) -> None:
        self._operational_store = operational_store or OperationalStore()
        self._models: dict[str, KaplanMeierFitter] = {}
        self._train_from_operational_store()

    def estimate_rul(self, asset_type: str, hours_in_service: float) -> float:
        """Estimate remaining operating hours for an asset type and usage."""
        normalized_type = self._normalize_asset_type(asset_type)
        hours = max(0.0, self._safe_float(hours_in_service))
        model = self._models.get(normalized_type)
        if model is None:
            return max(0.0, self._max_life_hours(normalized_type) - hours)

        remaining = self._remaining_hours_from_model(model, hours)
        return round(max(0.0, remaining), 2)

    def get_survival_curve(self, asset_type: str) -> list[tuple[float, float]]:
        """Return survival curve points as ``(hours, probability)`` tuples."""
        normalized_type = self._normalize_asset_type(asset_type)
        model = self._models.get(normalized_type)
        if model is None:
            max_life = self._max_life_hours(normalized_type)
            return [(0.0, 1.0), (max_life, 0.0)]

        curve = model.survival_function_
        points: list[tuple[float, float]] = []
        for idx, row in curve.iterrows():
            points.append(
                (
                    round(self._safe_float(idx), 3),
                    round(max(0.0, min(1.0, self._safe_float(row.iloc[0]))), 6),
                )
            )
        return points

    def _train_from_operational_store(self) -> None:
        assets = self._operational_store.get_assets()
        if not assets or KaplanMeierFitter is None:
            return

        durations_by_type: dict[str, list[float]] = defaultdict(list)
        observed_by_type: dict[str, list[bool]] = defaultdict(list)

        for asset in assets:
            asset_type = self._normalize_asset_type(getattr(asset, "asset_type", "OTHER"))
            asset_id = str(getattr(asset, "asset_id", "")).strip()
            operating_hours = max(1.0, self._safe_float(getattr(asset, "operating_hours", 0.0)))
            history = self._operational_store.get_maintenance_history(asset_id)
            failure_hours = self._latest_maintenance_hours(history)

            if failure_hours is None:
                durations_by_type[asset_type].append(operating_hours)
                observed_by_type[asset_type].append(False)
            else:
                durations_by_type[asset_type].append(max(1.0, failure_hours))
                observed_by_type[asset_type].append(True)

        for asset_type, durations in durations_by_type.items():
            if not durations:
                continue
            try:
                kmf = KaplanMeierFitter()
                # Tactical intent: convert maintenance interventions into observed
                # "failure" events to prioritize assets that need sustainment first.
                kmf.fit(
                    durations=durations,
                    event_observed=observed_by_type[asset_type],
                    label=asset_type,
                )
                self._models[asset_type] = kmf
            except Exception:
                continue

    def _remaining_hours_from_model(
        self, model: KaplanMeierFitter, hours_in_service: float
    ) -> float:
        current_hours = max(0.0, self._safe_float(hours_in_service))
        survival_now = self._safe_float(model.predict(current_hours))
        if survival_now <= 0.0:
            return 0.0

        curve = model.survival_function_
        timeline = [self._safe_float(idx) for idx in curve.index.tolist()]
        probabilities = [self._safe_float(value) for value in curve.iloc[:, 0].tolist()]

        future_hours = [current_hours]
        conditional_survival = [1.0]
        for hour_mark, probability in zip(timeline, probabilities):
            if hour_mark <= current_hours:
                continue
            future_hours.append(hour_mark)
            conditional_survival.append(max(0.0, min(1.0, probability / survival_now)))

        if len(future_hours) == 1:
            return 0.0

        remaining = 0.0
        for idx in range(1, len(future_hours)):
            delta = future_hours[idx] - future_hours[idx - 1]
            remaining += max(0.0, delta) * conditional_survival[idx - 1]
        return remaining

    @staticmethod
    def _latest_maintenance_hours(history: list[MaintenanceRecord]) -> float | None:
        if not history:
            return None

        latest: float | None = None
        for record in history:
            hours = ReliabilityAnalyzer._safe_float(getattr(record, "hours_at_maintenance", 0.0))
            if latest is None or hours > latest:
                latest = hours
        return latest

    def _max_life_hours(self, asset_type: str) -> float:
        return self._DEFAULT_MAX_LIFE_HOURS.get(asset_type, 6000.0)

    @staticmethod
    def _normalize_asset_type(asset_type: Any) -> str:
        if hasattr(asset_type, "value"):
            asset_type = getattr(asset_type, "value")
        normalized = str(asset_type).strip().upper()
        return normalized or "OTHER"

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

