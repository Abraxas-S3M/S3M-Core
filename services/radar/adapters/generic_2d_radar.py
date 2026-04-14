"""Adapter for 2D surveillance radars (range + azimuth only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Invalid timestamp format: {value!r}") from exc
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    raise ValueError("timestamp must be an ISO8601 string or datetime")


class Generic2DRadarAdapter(BaseRadarAdapter):
    """Adapter for 2D rotating surveillance radars.

    Military context:
    Many legacy and cost-effective radars provide only range and azimuth.
    They cannot determine target altitude. The adapter assigns elevation=0
    and marks has_elevation=False so downstream fusion can weight accordingly.
    """

    def parse_raw_data(self, raw_data: dict[str, Any]) -> list[RadarPlot]:
        if not isinstance(raw_data, dict):
            raise ValueError("raw_data must be a dictionary")

        plots_data = raw_data.get("plots", [raw_data])
        if not isinstance(plots_data, list):
            raise ValueError("plots must be a list when provided")

        results: list[RadarPlot] = []
        for plot_data in plots_data:
            if not isinstance(plot_data, dict):
                raise ValueError("each plot entry must be a dictionary")
            range_m_value = plot_data.get("range_m")
            if range_m_value is None:
                range_m_value = float(plot_data.get("range_km", 0.0)) * 1000.0

            plot = RadarPlot(
                radar_id=self.config.radar_id,
                timestamp=_parse_timestamp(plot_data.get("timestamp")),
                range_m=float(range_m_value),
                azimuth_deg=float(plot_data.get("azimuth_deg", plot_data.get("bearing_deg", 0.0))),
                elevation_deg=0.0,  # 2D radar: no elevation for tactical track.
                radial_velocity_mps=float(plot_data.get("velocity_mps", 0.0)),
                rcs_dbsm=float(plot_data.get("rcs_dbsm", 0.0)),
                snr_db=float(plot_data.get("snr_db", 15.0)),
                signal_strength=float(plot_data.get("signal_strength", 0.0)),
            )
            results.append(plot)
        return results

    def create_default_config(self) -> RadarConfig:
        return RadarConfig(
            name_en="Generic 2D Surveillance Radar",
            name_ar="رادار مراقبة ثنائي الأبعاد",
            radar_type=RadarType.GENERIC_2D,
            band=RadarBand.S_BAND,
            scan_mode=ScanMode.ROTATING,
            max_range_m=80_000,
            min_range_m=500,
            has_elevation=False,
            has_doppler=False,
            beam_width_az_deg=2.0,
            scan_rate_rpm=6.0,
            range_noise_std_m=100.0,
            azimuth_noise_std_deg=1.2,
        )
