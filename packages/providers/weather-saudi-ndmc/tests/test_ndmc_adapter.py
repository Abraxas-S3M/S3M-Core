from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.weather_saudi_ndmc.adapter import SaudiNDMCAdapter


def test_manifest_correct() -> None:
    manifest = SaudiNDMCAdapter(mode="airgapped").get_manifest()
    assert manifest.tier == "GOVERNMENT"


def test_metar_parsing() -> None:
    parsed = SaudiNDMCAdapter(mode="airgapped").normalizer.parse_metar("OERK 151430Z 32012KT 9999 FEW040 SCT200 46/08 Q1006")
    assert parsed["wind_dir_deg"] == 320
    assert parsed["wind_speed_kt"] == 12
    assert parsed["visibility_m"] == 10000
    assert parsed["temperature_c"] == 46


def test_metar_wind_conversion() -> None:
    parsed = SaudiNDMCAdapter(mode="airgapped").normalizer.parse_metar("OERK 151430Z 32012KT 9999 FEW040 SCT200 46/08 Q1006")
    obs = SaudiNDMCAdapter(mode="airgapped").normalizer.normalize_metar(parsed)
    assert round(obs.wind_speed_mps, 2) == 6.17


def test_metar_gust_parsing() -> None:
    parsed = SaudiNDMCAdapter(mode="airgapped").normalizer.parse_metar("OEKK 151430Z 32015G25KT 9999 FEW040 45/07 Q1006")
    assert parsed["wind_speed_kt"] == 15
    assert parsed["wind_gust_kt"] == 25


def test_metar_variable_wind() -> None:
    parsed = SaudiNDMCAdapter(mode="airgapped").normalizer.parse_metar("OEAB 151430Z VRB03KT 9999 SCT045 31/12 Q1012")
    assert parsed["wind_dir_deg"] is None
    assert parsed["wind_speed_kt"] == 3


def test_dust_code_detection() -> None:
    n = SaudiNDMCAdapter(mode="airgapped").normalizer
    assert n.detect_dust_from_metar(["SS"])["severity"] == "severe_storm"
    assert n.detect_dust_from_metar(["HZ"])["severity"] == "light"


def test_saudi_airports_defined() -> None:
    assert len(SaudiNDMCAdapter(mode="airgapped").config.saudi_airports) == 12


def test_airport_dust_conditions() -> None:
    data = SaudiNDMCAdapter(mode="airgapped").fetch_all_airport_metar()
    assert "OEJB" in data["dust_conditions"] and "OEYN" in data["dust_conditions"]


def test_ndmc_alert_bilingual() -> None:
    alerts = SaudiNDMCAdapter(mode="airgapped").fetch_alerts()["alerts"]
    assert all("description_en" in a and "description_ar" in a for a in alerts)


def test_humidity_from_temp_dewpoint() -> None:
    n = SaudiNDMCAdapter(mode="airgapped").normalizer
    rh = n._estimate_humidity_pct(46, 8)
    assert 5 <= rh <= 20


def test_file_based_ingestion() -> None:
    ingest = SaudiNDMCAdapter(mode="airgapped").ingest_from_directory()
    assert {"files_processed", "alerts", "metar_reports"}.issubset(ingest.keys())


def test_fetch_airgapped() -> None:
    data = SaudiNDMCAdapter(mode="airgapped").fetch_alerts()
    assert data["source"] == "file"
