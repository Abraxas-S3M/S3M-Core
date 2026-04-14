"""Adapter for RPS-202 vehicle-mounted medium-range surveillance radar.

Military context:
The RPS-202 is a vehicle-mounted radar used in the Krechet demo providing
medium-range surveillance. Mounted on the C3 VAN, it serves as the primary
search radar for the integrated air defense system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode


class RPS202Adapter(BaseRadarAdapter):
    """Adapter for RPS-202 class vehicle-mounted radar."""

    def parse_raw_data(self, raw_data: dict[str, Any]) -> list[RadarPlot]:
        if not isinstance(raw_data, dict):
            raise ValueError("raw_data must be a dictionary payload")

        plots_data = raw_data.get("plots", [raw_data])
        if not isinstance(plots_data, list):
            raise ValueError("plots field must be a list when present")

        results: list[RadarPlot] = []
        for index, payload in enumerate(plots_data):
            if not isinstance(payload, dict):
                raise ValueError(f"plot entry at index {index} must be a dictionary")

            plot = RadarPlot(
                radar_id=self.config.radar_id,
                timestamp=self._parse_timestamp(payload.get("timestamp")),
                range_m=self._parse_range_m(payload),
                azimuth_deg=self._parse_float(payload.get("azimuth_deg", payload.get("bearing_deg", 0.0)), "azimuth_deg"),
                elevation_deg=self._parse_float(payload.get("elevation_deg", 0.0), "elevation_deg"),
                radial_velocity_mps=self._parse_float(payload.get("velocity_mps", 0.0), "velocity_mps"),
                rcs_dbsm=self._parse_float(payload.get("rcs_dbsm", -5.0), "rcs_dbsm"),
                snr_db=self._parse_float(payload.get("snr_db", 18.0), "snr_db"),
            )
            results.append(plot)
        return results

    def create_default_config(self) -> RadarConfig:
        return RadarConfig(
            radar_id="rps202-c3-van",
            name_en="RPS-202 Vehicle-Mounted Radar",
            name_ar="رادار RPS-202 مركبة",
            radar_type=RadarType.RPS_202,
            band=RadarBand.S_BAND,
            scan_mode=ScanMode.ROTATING,
            max_range_m=50_000,
            min_range_m=200,
            max_elevation_deg=70.0,
            has_elevation=True,
            has_doppler=True,
            beam_width_az_deg=1.8,
            beam_width_el_deg=2.5,
            scan_rate_rpm=6.0,
            min_detectable_rcs_dbsm=-10.0,
            range_resolution_m=100.0,
            range_noise_std_m=50.0,
            azimuth_noise_std_deg=0.7,
            elevation_noise_std_deg=1.5,
        )

    @staticmethod
    def _parse_timestamp(raw_timestamp: Any) -> datetime:
        if raw_timestamp is None:
            return datetime.now(timezone.utc)
        if isinstance(raw_timestamp, datetime):
            if raw_timestamp.tzinfo is None:
                return raw_timestamp.replace(tzinfo=timezone.utc)
            return raw_timestamp
        if isinstance(raw_timestamp, str):
            parsed = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        raise ValueError("timestamp must be an ISO8601 string or datetime instance")

    @staticmethod
    def _parse_range_m(payload: dict[str, Any]) -> float:
        if "range_m" in payload:
            range_m = RPS202Adapter._parse_float(payload["range_m"], "range_m")
        else:
            range_km = RPS202Adapter._parse_float(payload.get("range_km", 0.0), "range_km")
            range_m = range_km * 1000.0
        if range_m < 0.0:
            raise ValueError("range must be non-negative")
        return range_m

    @staticmethod
    def _parse_float(value: Any, field_name: str) -> float:
        parsed = float(value)
        if not isfinite(parsed):
            raise ValueError(f"{field_name} must be a finite number")
        return parsed
