"""Generic 3D radar adapter for normalized tactical plot parsing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarPlot


class Generic3DRadarAdapter(BaseRadarAdapter):
    """Parses simple list-based 3D plot payloads."""

    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        if not isinstance(raw_data, dict):
            raise ValueError("raw_data must be a dictionary")

        payload = raw_data.get("plots", [])
        if not isinstance(payload, list):
            raise ValueError("raw_data['plots'] must be a list")

        plots: List[RadarPlot] = []
        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                continue

            try:
                range_m = self._to_float(item.get("range_m", item.get("range")))
                azimuth_deg = self._to_float(item.get("azimuth_deg", item.get("azimuth")))
            except ValueError:
                continue

            elevation_deg = self._safe_float(item.get("elevation_deg", item.get("elevation")), default=0.0)
            plot = RadarPlot(
                plot_id=str(item.get("plot_id", f"{self.config.radar_id}-{idx}")),
                range_m=range_m,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
                rcs_dbsm=self._safe_float(item.get("rcs_dbsm"), default=-30.0),
                radial_velocity_mps=self._safe_float(item.get("radial_velocity_mps"), default=0.0),
                snr_db=self._safe_float(item.get("snr_db"), default=0.0),
                timestamp=datetime.now(timezone.utc),
            )
            plots.append(plot)
        return plots

    def _to_float(self, value: Any) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError("value must be numeric")
        return float(value)

    def _safe_float(self, value: Any, default: float) -> float:
        return float(value) if isinstance(value, (int, float)) else default

