from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from integration_sdk.base.provider_adapter import OperatingMode
from packages.providers.maritime_vesselfinder.adapter import VesselFinderAdapter


def test_manifest_correct() -> None:
    m = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED).get_manifest()
    assert m.provider_id == "maritime-vesselfinder"
    assert m.tier.value == "freemium"
    assert m.auth_type == "api_key"


def test_speed_already_knots() -> None:
    adapter = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]["AIS"]
    track = adapter.normalizer.normalize_vessel(vessel)
    assert track.speed_knots == vessel["SPEED"]


def test_ais_type_range_mapping() -> None:
    n = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED).normalizer
    assert n._map_ais_type(81) == "Tanker"


def test_dimensions_from_abcd() -> None:
    adapter = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]["AIS"]
    track = adapter.normalizer.normalize_vessel(vessel)
    assert track.length_m == 333


def test_eta_parsing() -> None:
    n = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED).normalizer
    eta = n._parse_eta("0615 1800")
    assert eta is not None
    assert eta.month == 6 and eta.day == 15 and eta.hour == 18 and eta.minute == 0


def test_normalize_all_fields() -> None:
    adapter = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED)
    vessel = adapter.fetch_zone_vessels("persian_gulf")["vessels"][0]["AIS"]
    track = adapter.normalizer.normalize_vessel(vessel)
    assert track.mmsi and track.vessel_name and track.geo_point


def test_saudi_ports_defined() -> None:
    ports = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED).config.saudi_ports
    assert len(ports) == 6
    assert "JUBAIL" in ports


def test_fetch_airgapped() -> None:
    data = VesselFinderAdapter(mode=OperatingMode.AIRGAPPED).fetch_zone_vessels("persian_gulf")
    assert data["count"] == 20
