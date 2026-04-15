"""Tests for S3M interoperability symbology mapping."""

from services.interop.models import DISEntityType
from services.interop.symbology.sidc_generator import SIDCGenerator
from src.security.interop.dis_adapter import DIS_ENTITY_MAP


def _force_id_for_entity(entity_name: str) -> int:
    if entity_name.startswith("FRIENDLY_"):
        return 1
    if entity_name.startswith("ENEMY_"):
        return 2
    return 3


def test_generate_sidc_all_dis_entity_map_entries():
    for entity_name, payload in DIS_ENTITY_MAP.items():
        dis_type = DISEntityType(
            kind=payload["kind"],
            domain=payload["domain"],
            country=payload["country"],
            category=payload["category"],
            subcategory=payload.get("subcategory", 0),
            specific=0,
            extra=0,
        )
        sidc = SIDCGenerator.from_dis_entity_type(dis_type, force_id=_force_id_for_entity(entity_name))
        assert len(sidc) == 20
        assert sidc.isdigit()


def test_sidc_version_always_10():
    sidc = SIDCGenerator.generate(affiliation="friendly", domain="air", entity_type="FRIENDLY_UAV")
    assert sidc[:2] == "10"


def test_sidc_affiliation_friendly_is_3():
    sidc = SIDCGenerator.generate(affiliation="friendly", domain="land", entity_type="FRIENDLY_UGV")
    assert sidc[2] == "3"


def test_sidc_affiliation_hostile_is_6():
    sidc = SIDCGenerator.generate(affiliation="hostile", domain="land", entity_type="ENEMY_UGV")
    assert sidc[2] == "6"


def test_sidc_to_cot_type_roundtrip():
    original_sidc = SIDCGenerator.generate(
        affiliation="hostile",
        domain="surface",
        entity_type="ENEMY_SHIP",
    )
    cot_type = SIDCGenerator.to_cot_type(original_sidc)
    roundtrip_sidc = SIDCGenerator.from_cot_type(cot_type)
    assert roundtrip_sidc[2] == original_sidc[2]
    assert roundtrip_sidc[3:5] == original_sidc[3:5]


def test_from_dis_entity_type_uav():
    dis_type = DISEntityType(1, 2, 178, 1, 0, 0, 0)
    sidc = SIDCGenerator.from_dis_entity_type(dis_type, force_id=1)
    assert len(sidc) == 20
    assert sidc[3:5] == "01"


def test_sidc_length_always_20():
    sidcs = [
        SIDCGenerator.generate("friendly", "air", "FRIENDLY_UAV"),
        SIDCGenerator.generate("hostile", "land", "ENEMY_INFANTRY"),
        SIDCGenerator.generate("unknown", "space", "UNKNOWN"),
        SIDCGenerator.from_cot_type("a-f-G-U-C"),
    ]
    assert all(len(sidc) == 20 for sidc in sidcs)


def test_sidc_all_digits():
    sidcs = [
        SIDCGenerator.generate("friendly", "surface", "FRIENDLY_SHIP"),
        SIDCGenerator.generate("hostile", "subsurface", "UNKNOWN"),
        SIDCGenerator.from_cot_type("s-h-G-U-C"),
        SIDCGenerator.from_dis_entity_type(DISEntityType(1, 1, 0, 1, 0, 0, 0), force_id=2),
    ]
    assert all(sidc.isdigit() for sidc in sidcs)
