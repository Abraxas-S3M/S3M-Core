"""Adapter for 3D surveillance radars (range + azimuth + elevation)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode


class Generic3DRadarAdapter(BaseRadarAdapter):
    """Adapter for 3D rotating or electronic-scan surveillance radars."""

    def _parse_timestamp(self, value: Any) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        raise ValueError("timestamp must be an ISO-8601 string or datetime")

    def parse_raw_data(self, raw_data: dict[str, Any]) -> list[RadarPlot]:
        if not isinstance(raw_data, dict):
            raise ValueError("raw_data must be a dictionary payload")

        if "plots" in raw_data:
            plots_data = raw_data["plots"]
            if not isinstance(plots_data, list):
                raise ValueError("plots must be a list when provided")
        else:
            plots_data = [raw_data]

        results: list[RadarPlot] = []
        for index, payload in enumerate(plots_data):
            if not isinstance(payload, dict):
                raise ValueError(f"plot at index {index} must be a dictionary")

            range_m = payload.get("range_m")
            if range_m is None:
                range_km = payload.get("range_km", 0.0)
                range_m = float(range_km) * 1000.0

            # Keep permissive defaults to preserve tactical feed continuity
            # when optional fields are missing in legacy emitters.
            plot = RadarPlot(
                radar_id=self.config.radar_id,
                timestamp=self._parse_timestamp(payload.get("timestamp")),
                range_m=float(range_m),
                azimuth_deg=float(payload.get("azimuth_deg", payload.get("bearing_deg", 0.0))),
                elevation_deg=float(payload.get("elevation_deg", 0.0)),
                radial_velocity_mps=float(
                    payload.get("velocity_mps", payload.get("radial_velocity_mps", 0.0))
                ),
                rcs_dbsm=float(payload.get("rcs_dbsm", 0.0)),
                snr_db=float(payload.get("snr_db", 18.0)),
                signal_strength=float(payload.get("signal_strength", 0.0)),
            )
            results.append(plot)
        return results

    def create_default_config(self) -> RadarConfig:
        return RadarConfig(
            radar_id="generic_3d",
            name_en="Generic 3D Surveillance Radar",
            name_ar="رادار مراقبة ثلاثي الأبعاد",
            radar_type=RadarType.GENERIC_3D,
            band=RadarBand.S_BAND,
            scan_mode=ScanMode.ROTATING,
            max_range_m=60_000,
            min_range_m=300,
            has_elevation=True,
            has_doppler=True,
            beam_width_az_deg=1.5,
            beam_width_el_deg=2.0,
            scan_rate_rpm=6.0,
            range_noise_std_m=60.0,
            azimuth_noise_std_deg=0.8,
            elevation_noise_std_deg=1.0,
        )
