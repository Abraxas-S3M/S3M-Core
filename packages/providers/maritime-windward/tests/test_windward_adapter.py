from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from integration_sdk.base.provider_adapter import OperatingMode
from packages.providers.maritime_windward.adapter import WindwardAdapter


def test_manifest_correct() -> None:
    m = WindwardAdapter(mode=OperatingMode.AIRGAPPED).get_manifest()
    assert m.provider_id == "maritime-windward"
    assert m.tier.value == "premium"
    assert m.auth_type == "api_key"


def test_risk_level_thresholds() -> None:
    n = WindwardAdapter(mode=OperatingMode.AIRGAPPED).normalizer
    assert n._risk_level(72) == "high"
    assert n._risk_level(12) == "low"


def test_dark_activity_sets_is_dark() -> None:
    profile = WindwardAdapter(mode=OperatingMode.AIRGAPPED).fetch_vessel_risk("636092400")["profile"]
    track = WindwardAdapter(mode=OperatingMode.AIRGAPPED).normalizer.normalize_risk_profile(profile)
    assert track.is_dark is True


def test_clean_vessel_not_dark() -> None:
    profile = WindwardAdapter(mode=OperatingMode.AIRGAPPED).fetch_vessel_risk("311000987")["profile"]
    track = WindwardAdapter(mode=OperatingMode.AIRGAPPED).normalizer.normalize_risk_profile(profile)
    assert track.is_dark is False


def test_sanctions_screening() -> None:
    result = WindwardAdapter(mode=OperatingMode.AIRGAPPED).screen_fleet(["a", "b"])
    assert result["flagged"] == 2


def test_normalize_risk_to_tags() -> None:
    profile = WindwardAdapter(mode=OperatingMode.AIRGAPPED).fetch_vessel_risk("636092400")["profile"]
    tags = WindwardAdapter(mode=OperatingMode.AIRGAPPED).normalizer.normalize_risk_profile(profile).tags
    assert any(tag.startswith("indicator:dark_activity") for tag in tags)


def test_risk_to_border_alert_mapping() -> None:
    profile = WindwardAdapter(mode=OperatingMode.AIRGAPPED).fetch_vessel_risk("636092400")["profile"]
    alert = WindwardAdapter(mode=OperatingMode.AIRGAPPED).normalizer.risk_to_border_alert(profile)
    assert alert["alert_type"] == "dark_vessel"


def test_ownership_chain_structure() -> None:
    own = WindwardAdapter(mode=OperatingMode.AIRGAPPED).fetch_ownership("636092400")["ownership"]
    parsed = WindwardAdapter(mode=OperatingMode.AIRGAPPED).normalizer.normalize_ownership(own)
    assert parsed["beneficial_owner"] and parsed["registered_owner"] and parsed["operator"]


def test_fleet_screening_counts() -> None:
    result = WindwardAdapter(mode=OperatingMode.AIRGAPPED).screen_fleet(["x"])
    assert result["flagged"] + result["clean"] == 10


def test_fetch_airgapped() -> None:
    profile = WindwardAdapter(mode=OperatingMode.AIRGAPPED).fetch_vessel_risk("636092400")
    assert "profile" in profile
