"""Tests for TAXII 2.1 transport and STIX bridge workflows."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
import urllib.error

import pytest

import services.interop.stix.taxii_client as taxii_client_module
from services.interop.stix import STIXTAXIIBridge, TAXIIClient
from src.apps.intel.stix_processor import STIXProcessor
from src.apps.intel.watchlists import WatchlistStore


class _MockHTTPResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_MockHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb


def _request_headers(req: Any) -> dict[str, str]:
    return {k.lower(): v for k, v in req.header_items()}


def test_discover_parses_api_roots(monkeypatch) -> None:
    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        _ = req
        return _MockHTTPResponse(
            {
                "title": "Coalition TAXII",
                "description": "STIX exchange endpoint",
                "api_roots": ["/taxii2/root-a/", "http://partner.example/taxii2/root-b/"],
            }
        )

    monkeypatch.setattr(taxii_client_module.request, "urlopen", fake_urlopen)
    client = TAXIIClient("http://cti.example")
    payload = client.discover()

    assert payload["title"] == "Coalition TAXII"
    assert payload["description"] == "STIX exchange endpoint"
    assert payload["api_roots"] == [
        "http://cti.example/taxii2/root-a/",
        "http://partner.example/taxii2/root-b/",
    ]


def test_list_collections_returns_collection_objects(monkeypatch) -> None:
    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        _ = req
        return _MockHTTPResponse(
            {
                "collections": [
                    {
                        "id": "col-1",
                        "title": "CENTCOM",
                        "description": "Regional IOC feed",
                        "can_read": True,
                        "can_write": False,
                    }
                ]
            }
        )

    monkeypatch.setattr(taxii_client_module.request, "urlopen", fake_urlopen)
    client = TAXIIClient("http://cti.example")
    client.active_api_root = "http://cti.example/taxii2/root-a/"
    rows = client.list_collections()

    assert rows == [
        {
            "id": "col-1",
            "title": "CENTCOM",
            "description": "Regional IOC feed",
            "can_read": True,
            "can_write": False,
        }
    ]


def test_poll_returns_stix_objects(monkeypatch, tmp_path) -> None:
    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        _ = req
        return _MockHTTPResponse(
            {
                "type": "bundle",
                "id": "bundle--1234",
                "objects": [{"type": "indicator", "id": "indicator--1", "name": "IOC-1"}],
            }
        )

    monkeypatch.setattr(taxii_client_module.request, "urlopen", fake_urlopen)
    client = TAXIIClient(
        "http://cti.example",
        collection_id="col-1",
        outbox_dir=str(tmp_path / "outbox"),
        inbox_dir=str(tmp_path / "inbox"),
    )
    client.active_api_root = "http://cti.example/taxii2/root-a/"

    objects = client.poll(added_after="2026-04-01T00:00:00Z")
    assert len(objects) == 1
    assert objects[0]["type"] == "indicator"
    assert len(list((tmp_path / "inbox").glob("*.json"))) == 1


def test_publish_sends_correct_content_type(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        captured["request"] = req
        return _MockHTTPResponse({"status": "complete"})

    monkeypatch.setattr(taxii_client_module.request, "urlopen", fake_urlopen)
    client = TAXIIClient("http://cti.example", collection_id="col-1")
    client.active_api_root = "http://cti.example/taxii2/root-a/"

    ok = client.publish({"type": "bundle", "id": "bundle--a", "objects": []})
    assert ok is True
    headers = _request_headers(captured["request"])
    assert headers["content-type"] == "application/stix+json;version=2.1"


def test_offline_fallback_queues_to_outbox(monkeypatch, tmp_path) -> None:
    def failing_urlopen(req, timeout=10):  # noqa: ARG001
        _ = req
        raise urllib.error.URLError("link down")

    monkeypatch.setattr(taxii_client_module.request, "urlopen", failing_urlopen)
    outbox_dir = tmp_path / "outbox"
    client = TAXIIClient(
        "http://cti.example",
        collection_id="col-1",
        outbox_dir=str(outbox_dir),
        inbox_dir=str(tmp_path / "inbox"),
    )
    client.active_api_root = "http://cti.example/taxii2/root-a/"

    ok = client.publish({"type": "bundle", "id": "bundle--offline", "objects": []})
    assert ok is True
    queued_files = list(outbox_dir.glob("*.json"))
    assert len(queued_files) == 1
    queued_payload = json.loads(queued_files[0].read_text(encoding="utf-8"))
    assert queued_payload["bundle"]["id"] == "bundle--offline"


def test_bridge_sync_imports_to_watchlist(tmp_path) -> None:
    pytest.importorskip("stix2")

    class _FakeTAXIIClient:
        def __init__(self, objects: list[dict[str, Any]]) -> None:
            self._objects = objects

        def poll(self, collection_id: str | None = None) -> list[dict[str, Any]]:  # noqa: ARG002
            return list(self._objects)

        def publish(self, bundle: dict, collection_id: str | None = None) -> bool:  # noqa: ARG002
            _ = bundle
            return True

        def health_check(self) -> dict:
            return {"connected": False}

    processor = STIXProcessor()
    indicator = processor.create_indicator(
        name="IOC Alpha",
        pattern="[x-s3m-sites:name = 'Site-Alpha']",
        labels=["watchlist", "sites"],
    )
    actor = processor.create_threat_actor(name="Actor Bravo", aliases=["Bravo"], country="SA")
    polled_objects = [json.loads(indicator.serialize()), json.loads(actor.serialize())]

    watchlists = WatchlistStore(db_path=str(tmp_path / "watchlists.db"), stix_processor=processor)
    bridge = STIXTAXIIBridge(
        taxii_client=_FakeTAXIIClient(polled_objects),  # type: ignore[arg-type]
        stix_processor=processor,
        watchlist_store=watchlists,
    )

    result = bridge.sync_feed()
    assert result["new_indicators"] == 1
    assert result["new_threat_actors"] == 1
    assert not result["errors"]
    assert len(watchlists.list_sites()) == 1
    assert len(watchlists.list_orgs()) == 1


def test_auth_basic_and_token(monkeypatch) -> None:
    captured_headers: list[dict[str, str]] = []

    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        captured_headers.append(_request_headers(req))
        return _MockHTTPResponse({"api_roots": []})

    monkeypatch.setattr(taxii_client_module.request, "urlopen", fake_urlopen)

    basic = TAXIIClient(
        "http://cti.example",
        auth={"type": "basic", "username": "operator", "password": "secret"},
    )
    basic.discover()

    token = TAXIIClient(
        "http://cti.example",
        auth={"type": "token", "token": "abc123", "header": "X-TAXII-Token"},
    )
    token.discover()

    expected_basic = "Basic " + base64.b64encode(b"operator:secret").decode("ascii")
    assert captured_headers[0]["authorization"] == expected_basic
    assert captured_headers[1]["x-taxii-token"] == "abc123"
