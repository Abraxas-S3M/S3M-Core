"""Tests for local STIX processing used by surveillance watchlists."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("stix2")

from src.apps.intel.stix_processor import STIXProcessor


def test_create_indicator() -> None:
    processor = STIXProcessor()
    indicator = processor.create_indicator(
        name="Suspect Vessel",
        pattern="[x-s3m-vessels:name = 'Vessel-7']",
        labels=["watchlist", "vessels"],
    )
    raw = json.loads(indicator.serialize())
    assert raw["type"] == "indicator"
    assert raw["name"] == "Suspect Vessel"
    assert "watchlist" in raw["labels"]


def test_create_threat_actor() -> None:
    processor = STIXProcessor()
    actor = processor.create_threat_actor(
        name="Cell Echo",
        aliases=["Echo Unit"],
        country="SA",
    )
    raw = json.loads(actor.serialize())
    assert raw["type"] == "threat-actor"
    assert raw["name"] == "Cell Echo"
    assert "Echo Unit" in raw["aliases"]
    assert raw["x_mil_country"] == "SA"


def test_bundle_watchlist_and_import_bundle(tmp_path) -> None:
    processor = STIXProcessor()
    bundle = processor.bundle_watchlist(
        [
            {
                "id": "wl-person-1",
                "category": "persons",
                "name": "Person One",
                "aliases": ["P1"],
                "country": "SA",
            },
            {
                "id": "wl-vessel-1",
                "category": "vessels",
                "name": "Vessel One",
                "country": "SA",
            },
        ]
    )
    bundle_path = tmp_path / "watchlist_bundle.json"
    bundle_path.write_text(bundle.serialize(), encoding="utf-8")

    imported = processor.import_bundle(bundle_path)
    categories = {entry["category"] for entry in imported}
    names = {entry["name"] for entry in imported}
    assert categories == {"persons", "vessels"}
    assert names == {"Person One", "Vessel One"}
