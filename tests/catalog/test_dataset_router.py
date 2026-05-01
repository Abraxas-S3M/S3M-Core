from __future__ import annotations

from src.catalog.dataset_catalog import validate_catalog
from src.catalog.dataset_router import DatasetRouter


def _router() -> DatasetRouter:
    result = validate_catalog("catalog/datasets/saudi_mod.v1.json")
    assert result.is_valid, result.errors
    return DatasetRouter(result.records)


def test_route_risk_readiness_prioritizes_acled_and_ucdp() -> None:
    router = _router()
    routes = router.route(
        training_track="saudi_mod",
        scenario_domains=["risk_readiness"],
        top_k=8,
    )
    ids = [route.dataset_id for route in routes]
    assert "acled-saudi-conflict" in ids
    assert "ucdp-ged-saudi-yemen" in ids


def test_route_cop_intel_surfaces_geospatial_feeds() -> None:
    router = _router()
    routes = router.route(
        training_track="saudi_mod",
        scenario_domains=["cop_intel"],
        top_k=5,
    )
    ids = [route.dataset_id for route in routes]
    assert "gdelt-events-global-mena" in ids
    assert "acled-saudi-conflict" in ids


def test_route_cyber_ew_surfaces_cyber_datasets() -> None:
    router = _router()
    routes = router.route(
        training_track="saudi_mod",
        scenario_domains=["cyber_electronic_warfare"],
        top_k=8,
    )
    ids = [route.dataset_id for route in routes]
    assert "misp-cisa-mitre-oscd-cyber" in ids
    assert "nsl-kdd-network-intrusion" in ids


def test_route_logistics_surfaces_logistics_csv() -> None:
    router = _router()
    routes = router.route(
        training_track="saudi_mod",
        scenario_domains=["logistics_sustainment"],
        top_k=8,
    )
    ids = [route.dataset_id for route in routes]
    assert "logistics-csv-core" in ids


def test_route_bilingual_prefers_arabic_bilingual_sources() -> None:
    router = _router()
    routes = router.route(
        training_track="saudi_mod",
        scenario_domains=["bilingual"],
        top_k=6,
    )
    ids = [route.dataset_id for route in routes]
    assert "alghafa-arabic-benchmark" in ids
    assert "arabic-wikipedia-text" in ids
