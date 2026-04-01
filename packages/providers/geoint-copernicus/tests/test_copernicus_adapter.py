"""Tests for Copernicus provider adapter."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from packages.providers.geoint_copernicus.adapter import CopernicusAdapter
from packages.providers.geoint_copernicus.config import SAUDI_AOIS, CopernicusConfig
from packages.providers.geoint_copernicus.framework_compat import (
    ProviderCategory,
    ProviderRegistry,
    ProviderTier,
)
from packages.providers.geoint_copernicus.models import GeoPoint, NormalizedGeoObservation


class FakeClient:
    """Mock client for deterministic offline tests."""

    def __init__(self) -> None:
        self.post_calls = []
        self.get_calls = []
        self.token_payload = {"access_token": "fake-token", "expires_in": 600}
        self.search_payload = {"value": []}

    def post_form_json(self, url, data, headers=None):
        self.post_calls.append({"url": url, "data": data, "headers": headers})
        return dict(self.token_payload)

    def get_json(self, url, headers=None):
        self.get_calls.append({"url": url, "headers": headers})
        return dict(self.search_payload)


class CopernicusAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_airgapped = os.environ.get("S3M_AIRGAPPED")
        self._old_client_id = os.environ.get("COPERNICUS_CLIENT_ID")
        self._old_client_secret = os.environ.get("COPERNICUS_CLIENT_SECRET")
        os.environ.pop("S3M_AIRGAPPED", None)
        os.environ.pop("COPERNICUS_CLIENT_ID", None)
        os.environ.pop("COPERNICUS_CLIENT_SECRET", None)
        self.tmpdir = tempfile.mkdtemp(prefix="copernicus-tests-")
        self.prev_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self) -> None:
        os.chdir(self.prev_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        self._restore_env("S3M_AIRGAPPED", self._old_airgapped)
        self._restore_env("COPERNICUS_CLIENT_ID", self._old_client_id)
        self._restore_env("COPERNICUS_CLIENT_SECRET", self._old_client_secret)

    def _restore_env(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def _fixtures_dir(self) -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "fixtures"
        )

    def _load_fixture(self, filename: str) -> dict:
        fixture_path = self._fixtures_dir() / filename
        with fixture_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _seed_airgapped_cache(self, fixture_name: str = "sentinel1_search_response.json") -> Path:
        payload = self._load_fixture(fixture_name)
        target = Path("data/integrations/geoint-copernicus/2026-03-30")
        target.mkdir(parents=True, exist_ok=True)
        output_file = target / "search_20260330T101010Z.json"
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        return output_file

    def test_manifest_correct(self):
        manifest = CopernicusAdapter().get_manifest()
        self.assertEqual(manifest.provider_id, "geoint-copernicus")
        self.assertEqual(manifest.category, ProviderCategory.GEOINT)
        self.assertEqual(manifest.tier, ProviderTier.FREE)

    def test_required_env_vars(self):
        manifest = CopernicusAdapter().get_manifest()
        self.assertIn("COPERNICUS_CLIENT_ID", manifest.required_env_vars)
        self.assertIn("COPERNICUS_CLIENT_SECRET", manifest.required_env_vars)

    def test_validate_credentials_airgapped(self):
        self._seed_airgapped_cache()
        os.environ["S3M_AIRGAPPED"] = "true"
        adapter = CopernicusAdapter(client=FakeClient())
        self.assertTrue(adapter.validate_credentials())

    def test_validate_credentials_online_missing(self):
        os.environ["S3M_AIRGAPPED"] = "false"
        adapter = CopernicusAdapter(client=FakeClient())
        self.assertFalse(adapter.validate_credentials())

    def test_fetch_airgapped_returns_cached(self):
        self._seed_airgapped_cache()
        os.environ["S3M_AIRGAPPED"] = "1"
        adapter = CopernicusAdapter(client=FakeClient())
        out = adapter.fetch()
        self.assertGreater(out["total_results"], 0)
        self.assertIn("products", out)
        self.assertEqual(out["query"], "airgapped-cache")

    def test_fetch_online_mock(self):
        fake_client = FakeClient()
        fake_client.search_payload = self._load_fixture("sentinel1_search_response.json")
        os.environ["COPERNICUS_CLIENT_ID"] = "cid"
        os.environ["COPERNICUS_CLIENT_SECRET"] = "csecret"
        adapter = CopernicusAdapter(client=fake_client, config=CopernicusConfig())

        out = adapter.fetch(
            {
                "collection": "SENTINEL-1",
                "product_type": "GRD",
                "aoi": "persian_gulf",
                "days_back": 7,
                "max_results": 20,
            }
        )
        self.assertEqual(out["total_results"], 5)
        self.assertTrue(fake_client.get_calls)
        called_url = fake_client.get_calls[-1]["url"]
        self.assertIn("/Products?$filter=", called_url)
        self.assertIn("Collection/Name", called_url)
        self.assertIn("OData.CSC.Intersects", called_url)
        self.assertIn("POLYGON((48%2024", called_url.replace(" ", "%20"))
        self.assertRegex(called_url, r"ContentDate/Start%20gt%20\d{4}-\d{2}-\d{2}T00:00:00.000Z")

    def test_normalize_sentinel1_products(self):
        fixture = self._load_fixture("sentinel1_search_response.json")
        adapter = CopernicusAdapter(client=FakeClient())
        raw = {"products": fixture["value"]}
        observations = adapter.normalize(raw)
        self.assertTrue(observations)
        self.assertTrue(all(isinstance(item, NormalizedGeoObservation) for item in observations))
        self.assertEqual(observations[0].observation_type, "sar")
        self.assertIn("Sentinel-1", observations[0].satellite)
        self.assertEqual(observations[0].resolution_m, 10.0)

    def test_normalize_sentinel2_products(self):
        fixture = self._load_fixture("sentinel2_search_response.json")
        adapter = CopernicusAdapter(client=FakeClient())
        raw = {"products": fixture["value"]}
        observations = adapter.normalize(raw)
        self.assertEqual(observations[0].observation_type, "multispectral")
        self.assertEqual(observations[0].cloud_cover_pct, 5.0)
        self.assertEqual(observations[1].cloud_cover_pct, 15.0)
        self.assertEqual(observations[2].cloud_cover_pct, 45.0)

    def test_normalize_footprint_parsing(self):
        adapter = CopernicusAdapter(client=FakeClient())
        points = adapter.normalizer.parse_wkt_polygon("POLYGON((49.5 25.0, 51.0 25.0, 51.0 27.0, 49.5 27.0, 49.5 25.0))")
        self.assertEqual(len(points), 5)
        self.assertIsInstance(points[0], GeoPoint)
        self.assertAlmostEqual(points[0].lat, 25.0)
        self.assertAlmostEqual(points[0].lon, 49.5)

    def test_health_check_airgapped(self):
        os.environ["S3M_AIRGAPPED"] = "true"
        cache_file = self._seed_airgapped_cache()
        adapter = CopernicusAdapter(client=FakeClient())
        ok = adapter.health_check()
        self.assertIn(ok["status"], {"OK", "DEGRADED"})
        self.assertEqual(ok["mode"], "AIRGAPPED")

        stale_ts = (datetime.now(timezone.utc) - timedelta(days=8)).timestamp()
        os.utime(cache_file, (stale_ts, stale_ts))
        degraded = adapter.health_check()
        self.assertEqual(degraded["status"], "DEGRADED")

    def test_saudi_aois_defined(self):
        expected = {
            "persian_gulf",
            "red_sea",
            "red_sea_north",
            "bab_el_mandeb",
            "strait_of_hormuz",
            "gulf_of_aden",
            "full_saudi",
            "jubail_coast",
        }
        self.assertTrue(expected.issubset(set(SAUDI_AOIS.keys())))

    def test_persian_gulf_aoi_valid_wkt(self):
        wkt = SAUDI_AOIS["persian_gulf"]
        points = CopernicusAdapter(client=FakeClient()).normalizer.parse_wkt_polygon(wkt)
        self.assertGreaterEqual(len(points), 4)

    def test_adapter_registers_in_registry(self):
        # Adapter registers during module import; verify discoverability.
        provider_ids = ProviderRegistry.list_provider_ids()
        self.assertIn("geoint-copernicus", provider_ids)


if __name__ == "__main__":
    unittest.main()
