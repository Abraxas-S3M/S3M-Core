"""Unit tests for tactical SIDC generation."""

from src.sensor_fusion.sidc_generator import generate_sidc


def test_generate_sidc_friendly_air():
    sidc = generate_sidc(affiliation="friendly", domain="air", entity_type="UAV")
    assert sidc == "10033000000000000000"


def test_generate_sidc_hostile_cyber():
    sidc = generate_sidc(affiliation="hostile", domain="cyber", entity_type="network intrusion")
    assert sidc == "10067000000000000000"


def test_generate_sidc_unknown_defaults():
    sidc = generate_sidc(affiliation=None, domain=None, entity_type=None)
    assert sidc == "10012000000000000000"


def test_generate_sidc_infers_domain_from_entity_type():
    sidc = generate_sidc(affiliation="friendly", domain="not-a-domain", entity_type="enemy submarine")
    assert sidc == "10035000000000000000"


def test_generate_sidc_always_returns_20_digits():
    sidc = generate_sidc(affiliation="???", domain="???", entity_type={"bad": "type"})  # type: ignore[arg-type]
    assert sidc.isdigit()
    assert len(sidc) == 20
