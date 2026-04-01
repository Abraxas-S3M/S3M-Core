from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.sim_sensorthings.adapter import SensorThingsAdapter
from packages.providers.sim_sensorthings.config import S3M_SENSOR_TYPES


def test_manifest_correct() -> None:
    manifest = SensorThingsAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "sim-sensorthings"
    assert manifest.category == "C4I_INTEROP"
    assert manifest.tier == "OPEN_STANDARD"
    assert manifest.auth_type == "none"


def test_sensor_types_defined() -> None:
    assert len(S3M_SENSOR_TYPES) == 7
    for key in [
        "ground_radar",
        "weather_station",
        "seismic_sensor",
        "chemical_detector",
        "radiation_monitor",
        "acoustic_sensor",
        "ais_receiver",
    ]:
        assert key in S3M_SENSOR_TYPES
        assert len(S3M_SENSOR_TYPES[key]["properties"]) >= 3


def test_normalize_observation_to_sensor_reading() -> None:
    adapter = SensorThingsAdapter(mode="airgapped")
    obs = adapter.get_observations(limit=1)[0]
    norm = adapter.normalizer.normalize_observation(obs)
    assert {"sensor_id", "sensor_type", "property", "value", "timestamp", "position", "unit", "quality"}.issubset(norm.keys())


def test_register_sensor_creates_datastreams() -> None:
    adapter = SensorThingsAdapter(mode="airgapped")
    out = adapter.register_s3m_sensor("ground_radar", "Radar-A", (24.71, 46.68, 615.0))
    assert out["sensor_type"] == "ground_radar"
    assert len(out["datastreams"]) == len(S3M_SENSOR_TYPES["ground_radar"]["properties"])


def test_stub_mode_available() -> None:
    adapter = SensorThingsAdapter(mode="airgapped")
    assert adapter.validate_credentials() is True
    assert adapter.health_check()["stub_mode"] is True


def test_feed_to_sensor_fusion_bridge() -> None:
    adapter = SensorThingsAdapter(mode="airgapped")
    readings = adapter.feed_to_sensor_fusion(adapter.get_observations(limit=3))
    assert len(readings) == 3
    assert all("sensor_id" in row for row in readings)


def test_fetch_airgapped() -> None:
    adapter = SensorThingsAdapter(mode="airgapped")
    things = adapter.fetch({"action": "things"})
    assert len(things) >= 1
