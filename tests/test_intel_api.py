#!/usr/bin/env python3
"""API tests for Phase 19 intelligence endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


client = TestClient(app)


def _seed_data() -> None:
    client.post("/intel/sources/defaults")
    client.post("/intel/warnings/defaults")
    client.post("/intel/collect")


def test_post_intel_collect_200():
    resp = client.post("/intel/collect")
    assert resp.status_code == 200
    assert "collection" in resp.json()


def test_get_intel_items_200():
    _seed_data()
    resp = client.get("/intel/items")
    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload


def test_post_sources_defaults_200_with_12_sources():
    resp = client.post("/intel/sources/defaults")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 12


def test_get_sources_200():
    resp = client.get("/intel/sources")
    assert resp.status_code == 200


def test_post_brief_daily_200_with_brief():
    resp = client.post("/intel/brief/daily", json={})
    assert resp.status_code == 200
    assert "brief_id" in resp.json()


def test_post_report_sitrep_200_with_report():
    resp = client.post("/intel/report/sitrep", json={"report_type": "SITREP", "region": "Red Sea"})
    assert resp.status_code == 200
    assert "report_id" in resp.json()


def test_get_crises_200():
    resp = client.get("/intel/crises")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_post_warnings_defaults_200_with_8_indicators():
    resp = client.post("/intel/warnings/defaults")
    assert resp.status_code == 200
    assert len(resp.json()) >= 8


def test_get_warnings_200():
    resp = client.get("/intel/warnings")
    assert resp.status_code == 200


def test_get_overview_200():
    resp = client.get("/intel/overview")
    assert resp.status_code == 200
    assert "items_last_24h" in resp.json()


def test_get_region_persian_gulf_200():
    resp = client.get("/intel/region/Persian Gulf")
    assert resp.status_code == 200
    assert resp.json()["region"] == "Persian Gulf"


def test_get_status_200():
    resp = client.get("/intel/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "operational"
