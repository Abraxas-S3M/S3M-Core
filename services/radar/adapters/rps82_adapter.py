"""Adapter for RPS-82 portable short-range surveillance radar.

Military context:
The RPS-82 is a portable, tripod-mounted radar used in the Krechet demo
at the LIPA training ground. It provides short-range air surveillance
with rapid deployment capability. Typical use: forward detection element.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Dict, List

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode


def _as_finite_float(value: Any, *, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a numeric value") from exc
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string or datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO-8601") from exc
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class RPS82Adapter(BaseRadarAdapter):
    """Adapter for RPS-82 class portable radar."""

    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        if not isinstance(raw_data, dict):
            raise ValueError("raw_data must be a dictionary")

        plots_field = raw_data.get("plots")
        if plots_field is None:
            plots_data: List[Dict[str, Any]] = [raw_data]
        elif isinstance(plots_field, list):
            plots_data = plots_field
        else:
            raise ValueError("raw_data['plots'] must be a list when provided")

        results: List[RadarPlot] = []
        for idx, payload in enumerate(plots_data):
            if not isinstance(payload, dict):
                raise ValueError(f"plot at index {idx} must be a dictionary")

            if "range_m" in payload:
                range_m = _as_finite_float(payload.get("range_m"), field_name="range_m")
            else:
                range_km = _as_finite_float(payload.get("range_km", 0.0), field_name="range_km")
                range_m = range_km * 1000.0

            plot = RadarPlot(
                radar_id=self.config.radar_id,
                timestamp=_parse_timestamp(payload.get("timestamp")),
                range_m=range_m,
                azimuth_deg=_as_finite_float(payload.get("azimuth_deg", payload.get("bearing_deg", 0.0)), field_name="azimuth_deg"),
                elevation_deg=_as_finite_float(payload.get("elevation_deg", 0.0), field_name="elevation_deg"),
                radial_velocity_mps=_as_finite_float(payload.get("velocity_mps", 0.0), field_name="velocity_mps"),
                rcs_dbsm=_as_finite_float(payload.get("rcs_dbsm", -10.0), field_name="rcs_dbsm"),
                snr_db=_as_finite_float(payload.get("snr_db", 12.0), field_name="snr_db"),
            )
            results.append(plot)

        return results

    def create_default_config(self) -> RadarConfig:
        return RadarConfig(
            radar_id="rps82-default",
            name_en="RPS-82 Portable Radar",
            name_ar="رادار RPS-82 محمول",
            radar_type=RadarType.RPS_82,
            band=RadarBand.X_BAND,
            scan_mode=ScanMode.ROTATING,
            max_range_m=20_000,
            min_range_m=100,
            max_elevation_deg=60.0,
            has_elevation=True,
            has_doppler=True,
            beam_width_az_deg=2.5,
            beam_width_el_deg=3.0,
            scan_rate_rpm=12.0,
            min_detectable_rcs_dbsm=-15.0,
            range_resolution_m=75.0,
            range_noise_std_m=75.0,
            azimuth_noise_std_deg=1.0,
            elevation_noise_std_deg=2.0,
        )
