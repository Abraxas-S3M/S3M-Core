"""Normalizer for Saudi NDMC alert and METAR weather data."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.weather.models import NormalizedWeatherObservation

from .config import METAR_DUST_CODES


class SaudiNDMCNormalizer:
    provider_id = "weather-saudi-ndmc"
    provider_name = "Saudi National Center of Meteorology"

    def _estimate_humidity_pct(self, temperature_c: float, dewpoint_c: float) -> float:
        # Tactical note: humidity estimate supports heat-stress planning in desert deployments.
        a = 17.625
        b = 243.04
        alpha_t = (a * temperature_c) / (b + temperature_c)
        alpha_td = (a * dewpoint_c) / (b + dewpoint_c)
        rh = 100.0 * math.exp(alpha_td - alpha_t)
        return max(0.0, min(100.0, rh))

    def parse_metar(self, raw_metar: str) -> dict[str, Any]:
        parts = raw_metar.split()
        if len(parts) < 5:
            raise ValueError("Invalid METAR string")
        station = parts[0]
        ts_token = next((p for p in parts if re.match(r"^\d{6}Z$", p)), "010000Z")
        wind_token = next((p for p in parts if p.endswith("KT")), "00000KT")
        vis_token = next((p for p in parts if p.isdigit()), "9999")
        temp_dew = next((p for p in parts if "/" in p and (p[0].isdigit() or p.startswith("M"))), "0/0")
        pressure_token = next((p for p in parts if p.startswith("Q") and p[1:].isdigit()), "Q1013")
        weather_phenomena = [p for p in parts if any(code in p for code in METAR_DUST_CODES)]
        clouds = [p for p in parts if p.startswith(("FEW", "SCT", "BKN", "OVC"))]

        wind_dir_deg: int | None = None
        wind_speed_kt = 0
        wind_gust_kt: int | None = None
        if wind_token.startswith("VRB"):
            wind_dir_deg = None
            m = re.match(r"^VRB(\d{2})(G(\d{2}))?KT$", wind_token)
            if m:
                wind_speed_kt = int(m.group(1))
                wind_gust_kt = int(m.group(3)) if m.group(3) else None
        else:
            m = re.match(r"^(\d{3})(\d{2})(G(\d{2}))?KT$", wind_token)
            if m:
                wind_dir_deg = int(m.group(1))
                wind_speed_kt = int(m.group(2))
                wind_gust_kt = int(m.group(4)) if m.group(4) else None

        day = int(ts_token[0:2])
        hour = int(ts_token[2:4])
        minute = int(ts_token[4:6])
        now = datetime.now(timezone.utc)
        timestamp = now.replace(day=min(day, 28), hour=hour, minute=minute, second=0, microsecond=0)

        temp_s, dew_s = temp_dew.split("/", 1)
        temperature_c = float(temp_s.replace("M", "-"))
        dewpoint_c = float(dew_s.replace("M", "-"))
        pressure_hpa = float(pressure_token[1:])
        visibility_m = 10000 if vis_token == "9999" else int(vis_token)

        return {
            "airport": station,
            "timestamp": timestamp.isoformat(),
            "wind_dir_deg": wind_dir_deg,
            "wind_speed_kt": wind_speed_kt,
            "wind_gust_kt": wind_gust_kt,
            "visibility_m": visibility_m,
            "temperature_c": temperature_c,
            "dewpoint_c": dewpoint_c,
            "pressure_hpa": pressure_hpa,
            "clouds": clouds,
            "weather_phenomena": weather_phenomena,
            "raw_metar": raw_metar,
        }

    def detect_dust_from_metar(self, weather_phenomena: list[str]) -> dict[str, Any]:
        joined = " ".join(weather_phenomena)
        if "SS" in joined:
            return {"dust_present": True, "severity": "severe_storm"}
        if "DS" in joined:
            return {"dust_present": True, "severity": "storm"}
        if "SA" in joined or "BLSA" in joined:
            return {"dust_present": True, "severity": "heavy"}
        if "DU" in joined or "BLDU" in joined:
            return {"dust_present": True, "severity": "moderate"}
        if "HZ" in joined:
            return {"dust_present": True, "severity": "light"}
        return {"dust_present": False, "severity": "none"}

    def normalize_metar(self, metar_data: dict[str, Any]) -> NormalizedWeatherObservation:
        humidity = self._estimate_humidity_pct(float(metar_data["temperature_c"]), float(metar_data["dewpoint_c"]))
        dust_flag = self.detect_dust_from_metar(list(metar_data.get("weather_phenomena", [])))
        tags = [str(metar_data.get("airport", "unknown"))] + list(metar_data.get("weather_phenomena", []))
        if dust_flag["dust_present"]:
            tags.append("dust_reported")
        return NormalizedWeatherObservation(
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(metar_data.get("airport")),
                confidence=0.98,
                classification="UNCLASSIFIED",
            ),
            timestamp=datetime.fromisoformat(str(metar_data["timestamp"]).replace("Z", "+00:00")),
            geo_point=GeoPoint(lat=24.71, lon=46.68),
            tags=tags,
            temperature_c=float(metar_data["temperature_c"]),
            humidity_pct=humidity,
            wind_speed_mps=float(metar_data["wind_speed_kt"]) * 0.5144,
            wind_direction_deg=float(metar_data["wind_dir_deg"] or 0.0),
            visibility_km=float(metar_data["visibility_m"]) / 1000.0,
            precipitation_mm=0.0,
            pressure_hpa=float(metar_data["pressure_hpa"]),
            cloud_cover_pct=0.0,
            uv_index=None,
            dust_concentration=None,
            forecast_hours=0,
        )

    def normalize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        return {
            "alert_type": alert.get("alert_type"),
            "severity": alert.get("severity", "yellow"),
            "regions_affected": list(alert.get("regions_affected", [])),
            "valid_from": alert.get("valid_from"),
            "valid_until": alert.get("valid_until"),
            "description_en": alert.get("description_en", ""),
            "description_ar": alert.get("description_ar", ""),
        }
