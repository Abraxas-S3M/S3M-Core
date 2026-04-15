"""Unit tests for STANAG 4559 NSILI catalog and product manager."""

from __future__ import annotations

from pathlib import Path

from services.interop.nsili import NSILICatalog, NSILIProductManager
from src.apps.intel.models import ReportType


def _catalog_config(tmp_path: Path) -> dict:
    return {
        "catalog_dir": str(tmp_path / "nsili_catalog"),
        "max_products": 10000,
        "default_classification": "UNCLASSIFIED",
        "partner_catalogs": [],
    }


def test_register_and_query_intsum(tmp_path) -> None:
    catalog = NSILICatalog(config=_catalog_config(tmp_path))
    product_id = catalog.register_product(
        {
            "productId": "rep-intsum-001",
            "productType": "INTSUM",
            "dateCreated": "2026-04-15T10:00:00+00:00",
            "classification": "FOUO",
            "spatialCoverage": (20.0, 40.0, 30.0, 50.0),
            "creator": "S3M INTEL CENTER",
            "title": "INTSUM - 24h",
            "format": "application/json",
            "content": {"body_en": "summary"},
        }
    )
    assert product_id == "rep-intsum-001"

    rows = catalog.query(product_type="INTSUM")
    assert len(rows) == 1
    assert rows[0]["productId"] == "rep-intsum-001"


def test_query_by_bounding_box(tmp_path) -> None:
    catalog = NSILICatalog(config=_catalog_config(tmp_path))
    catalog.register_product(
        {
            "productId": "img-001",
            "productType": "IMAGERY",
            "dateCreated": "2026-04-15T10:00:00+00:00",
            "classification": "UNCLASSIFIED",
            "spatialCoverage": (24.0, 46.0, 25.0, 47.0),
            "creator": "ISR SAT-7",
            "title": "Satellite pass",
            "format": "image/tiff",
        }
    )
    catalog.register_product(
        {
            "productId": "img-002",
            "productType": "IMAGERY",
            "dateCreated": "2026-04-15T11:00:00+00:00",
            "classification": "UNCLASSIFIED",
            "spatialCoverage": (10.0, 10.0, 11.0, 11.0),
            "creator": "ISR SAT-9",
            "title": "Non-overlap",
            "format": "image/jpeg",
        }
    )

    rows = catalog.query(bbox=(24.5, 46.5, 26.0, 48.0))
    assert len(rows) == 1
    assert rows[0]["productId"] == "img-001"


def test_query_by_classification(tmp_path) -> None:
    catalog = NSILICatalog(config=_catalog_config(tmp_path))
    catalog.register_product(
        {
            "productId": "rep-secret",
            "productType": "REPORT",
            "dateCreated": "2026-04-15T10:00:00+00:00",
            "classification": "SECRET",
            "creator": "S3M",
            "title": "Sensitive report",
            "format": "text/plain",
        }
    )
    catalog.register_product(
        {
            "productId": "rep-unclass",
            "productType": "REPORT",
            "dateCreated": "2026-04-15T10:10:00+00:00",
            "classification": "UNCLASSIFIED",
            "creator": "S3M",
            "title": "Routine report",
            "format": "text/plain",
        }
    )

    rows = catalog.query(classification="SECRET")
    assert [row["productId"] for row in rows] == ["rep-secret"]


def test_nsili_xml_roundtrip(tmp_path) -> None:
    catalog = NSILICatalog(config=_catalog_config(tmp_path))
    source_rows = [
        {
            "productId": "rep-xml-1",
            "productType": "REPORT",
            "dateCreated": "2026-04-15T10:00:00+00:00",
            "classification": "FOUO",
            "spatialCoverage": (24.0, 46.0, 25.0, 47.0),
            "creator": "S3M",
            "title": "XML test report",
            "format": "application/json",
            "contentRef": "products/rep-xml-1.json",
        },
        {
            "productId": "vid-xml-1",
            "productType": "VIDEO",
            "dateCreated": "2026-04-15T10:05:00+00:00",
            "classification": "UNCLASSIFIED",
            "spatialCoverage": None,
            "creator": "S3M",
            "title": "XML test video",
            "format": "video/mp4",
            "contentRef": "products/vid-xml-1.bin",
        },
    ]
    xml_payload = catalog.to_nsili_xml(source_rows)
    parsed_rows = catalog.from_nsili_xml(xml_payload)
    assert len(parsed_rows) == 2

    parsed_by_id = {row["productId"]: row for row in parsed_rows}
    assert parsed_by_id["rep-xml-1"]["productType"] == "REPORT"
    assert parsed_by_id["rep-xml-1"]["classification"] == "FOUO"
    assert parsed_by_id["rep-xml-1"]["spatialCoverage"] == (24.0, 46.0, 25.0, 47.0)
    assert parsed_by_id["vid-xml-1"]["productType"] == "VIDEO"


def test_intel_product_type_mapping(tmp_path) -> None:
    catalog = NSILICatalog(config=_catalog_config(tmp_path))
    manager = NSILIProductManager(catalog=catalog)

    for report_type in ReportType:
        product_id = manager.ingest_intel_product(
            {
                "report_id": f"rep-{report_type.value.lower()}",
                "report_type": report_type,
                "classification": "FOUO",
                "title": report_type.value,
                "body_en": f"{report_type.value} body",
            }
        )
        row = catalog.get_product(product_id)
        assert row["productType"] in {"REPORT", "IMAGERY", "VIDEO", "INTSUM"}


def test_empty_query_returns_all(tmp_path) -> None:
    catalog = NSILICatalog(config=_catalog_config(tmp_path))
    catalog.register_product(
        {
            "productId": "rep-all-1",
            "productType": "REPORT",
            "dateCreated": "2026-04-15T10:00:00+00:00",
            "classification": "UNCLASSIFIED",
            "creator": "S3M",
            "title": "A",
            "format": "text/plain",
        }
    )
    catalog.register_product(
        {
            "productId": "rep-all-2",
            "productType": "REPORT",
            "dateCreated": "2026-04-15T10:05:00+00:00",
            "classification": "UNCLASSIFIED",
            "creator": "S3M",
            "title": "B",
            "format": "text/plain",
        }
    )

    rows = catalog.query()
    assert len(rows) == 2
