from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.weather_cams.adapter import CAMSAdapter


def test_manifest_correct() -> None:
    manifest = CAMSAdapter(mode="airgapped").get_manifest()
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "api_key"


def test_dust_aod_thresholds_defined() -> None:
    thresholds = CAMSAdapter(mode="airgapped").config.dust_aod_thresholds
    assert all(key in thresholds for key in ["clear", "light_haze", "moderate_dust", "heavy_dust", "sandstorm", "severe_storm"])


def test_classify_dust_risk() -> None:
    n = CAMSAdapter(mode="airgapped").normalizer
    assert n.classify_dust_risk(0.08) == "clear"
    assert n.classify_dust_risk(0.4) == "moderate_dust"
    assert n.classify_dust_risk(2.3) == "severe_storm"


def test_visibility_from_aod() -> None:
    n = CAMSAdapter(mode="airgapped").normalizer
    assert round(n.estimate_visibility_from_aod(0.1), 1) == 20.0
    assert round(n.estimate_visibility_from_aod(2.0), 1) == 1.5


def test_dust_alert_generated() -> None:
    adapter = CAMSAdapter(mode="airgapped")
    data = adapter.fetch_dust_forecast("riyadh", 72)
    timeline = [{"timestamp": t, "aod": a, "pm10": p} for t, a, p in zip(data["timestamps"], data["dust_aod"], data["pm10"])]
    alerts = adapter.normalizer.generate_dust_alerts(timeline, adapter.config.dust_aod_thresholds)
    assert any(a["severity"] == "critical" for a in alerts)


def test_normalize_dust_concentration() -> None:
    obs = CAMSAdapter(mode="airgapped").normalize(CAMSAdapter(mode="airgapped").fetch_dust_forecast("riyadh", 24))["observations"][0]
    assert obs.dust_concentration is not None


def test_all_saudi_locations_dust() -> None:
    data = CAMSAdapter(mode="airgapped").fetch_all_saudi_dust(24)
    assert len(data["locations"]) == 12


def test_peak_dust_identified() -> None:
    data = CAMSAdapter(mode="airgapped").fetch_all_saudi_dust(24)
    assert data["peak_dust_location"] in data["locations"]
    assert data["peak_dust_aod"] >= 0.0


def test_fetch_airgapped() -> None:
    data = CAMSAdapter(mode="airgapped").fetch_dust_forecast("riyadh", 12)
    assert "timestamps" in data
