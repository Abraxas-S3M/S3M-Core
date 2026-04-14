"""Adapter for Western AESA-class radars (AN/TPS-80, Giraffe, TRML-4D class).

Military context:
Modern Western AESA radars offer the highest accuracy measurements with
electronic beam steering, rapid update rates, and excellent small-target
detection. These represent the premium sensor tier in a Krechet-equivalent
integrated air defense system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode


class WesternAESAAdapter(BaseRadarAdapter):
    """Adapter for Western AESA-class surveillance/tracking radars."""

    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        plots_data = raw_data.get("plots", raw_data.get("detections", [raw_data]))
        results = []
        for p in plots_data:
            plot = RadarPlot(
                radar_id=self.config.radar_id,
                timestamp=datetime.fromisoformat(p["timestamp"]) if "timestamp" in p else datetime.now(timezone.utc),
                range_m=float(p.get("range_m", p.get("range_km", 0) * 1000)),
                azimuth_deg=float(p.get("azimuth_deg", p.get("bearing_deg", 0))),
                elevation_deg=float(p.get("elevation_deg", 0)),
                radial_velocity_mps=float(p.get("velocity_mps", p.get("radial_velocity_mps", 0))),
                rcs_dbsm=float(p.get("rcs_dbsm", 0)),
                snr_db=float(p.get("snr_db", 25.0)),
                signal_strength=float(p.get("signal_strength", 0)),
            )
            results.append(plot)
        return results

    def create_default_config(self) -> RadarConfig:
        return RadarConfig(
            name_en="Western AESA Surveillance Radar",
            name_ar="رادار مسح إلكتروني غربي",
            radar_type=RadarType.AESA_WESTERN,
            band=RadarBand.C_BAND,
            scan_mode=ScanMode.ELECTRONIC,
            max_range_m=75_000,
            min_range_m=100,
            max_elevation_deg=80.0,
            has_elevation=True,
            has_doppler=True,
            beam_width_az_deg=0.8,
            beam_width_el_deg=1.0,
            scan_rate_rpm=0.0,
            update_rate_hz=2.0,
            min_detectable_rcs_dbsm=-20.0,
            range_resolution_m=30.0,
            azimuth_resolution_deg=0.5,
            velocity_resolution_mps=2.0,
            range_noise_std_m=15.0,
            azimuth_noise_std_deg=0.3,
            elevation_noise_std_deg=0.4,
        )

