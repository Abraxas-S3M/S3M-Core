from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from integration_sdk.base.provider_adapter import OperatingMode
from packages.providers.maritime_spire.adapter import SpireMaritimeAdapter
from packages.providers.maritime_spire.config import ZONE_CENTERS


def test_manifest_correct() -> None:
    m = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED).get_manifest()
    assert m.provider_id == "maritime-spire"
    assert m.tier.value == "premium"
    assert m.auth_type == "api_key"


def test_zone_centers_defined() -> None:
    assert len(ZONE_CENTERS) == 6
    assert set(ZONE_CENTERS["persian_gulf"].keys()) == {"lat", "lon", "radius_m"}


def test_normalize_nested_structure() -> None:
    adapter = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]
    track = adapter.normalizer.normalize_vessel(vessel)
    assert abs(track.geo_point.lat - vessel["position"]["latitude"]) < 1e-6


def test_satellite_only_dark_flag() -> None:
    adapter = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED)
    satellite_only = adapter.fetch_zone_vessels("persian_gulf")["vessels"][-1]
    track = adapter.normalizer.normalize_vessel(satellite_only)
    assert track.is_dark is True


def test_terrestrial_not_dark() -> None:
    adapter = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED)
    terrestrial = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]
    track = adapter.normalizer.normalize_vessel(terrestrial)
    assert track.is_dark is False


def test_confidence_satellite_vs_terrestrial() -> None:
    adapter = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED)
    terrestrial = adapter.normalizer.normalize_vessel(adapter.fetch_zone_vessels("persian_gulf")["vessels"][0])
    satellite = adapter.normalizer.normalize_vessel(adapter.fetch_zone_vessels("persian_gulf")["vessels"][-1])
    assert terrestrial.provenance.confidence == 0.95
    assert satellite.provenance.confidence == 0.85


def test_collection_type_classification() -> None:
    n = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED).normalizer
    payload = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED).fetch_zone_vessels("persian_gulf")["vessels"]
    assert n.classify_collection_type(payload[0]) == "terrestrial"
    assert n.classify_collection_type(payload[11]) == "mixed"
    assert n.classify_collection_type(payload[-1]) == "satellite"


def test_pagination_handling() -> None:
    data = SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED).fetch_zone_vessels("persian_gulf")
    assert data["count"] == 15


def test_fetch_airgapped() -> None:
    assert SpireMaritimeAdapter(mode=OperatingMode.AIRGAPPED).fetch_zone_vessels("persian_gulf")["count"] > 0
