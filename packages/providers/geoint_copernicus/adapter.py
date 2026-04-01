"""Copernicus Open Access Hub provider adapter.

Tactical context:
- Supports Sentinel product discovery for Saudi maritime and border-relevant AOIs
  used in S3M SAR detection and GEOINT workflows in online and air-gapped modes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .config import CopernicusConfig
from .framework_compat import (
    ProviderAdapter,
    ProviderCategory,
    ProviderManifest,
    ProviderRegistry,
    ProviderTier,
    ResilientClient,
    SecretProvider,
)
from .models import NormalizedGeoObservation
from .normalizer import CopernicusNormalizer

logger = logging.getLogger(__name__)


class CopernicusAdapter(ProviderAdapter):
    """Adapter for Copernicus Data Space Ecosystem OData search."""

    def __init__(
        self,
        config: Optional[CopernicusConfig] = None,
        secret_provider: Optional[SecretProvider] = None,
        client: Optional[ResilientClient] = None,
    ) -> None:
        self.config = config or CopernicusConfig()
        self.secret_provider = secret_provider or SecretProvider()
        self.client = client or ResilientClient(timeout_seconds=self.config.timeout_seconds)
        self.normalizer = CopernicusNormalizer()
        self._token: Optional[str] = None
        self._token_expiry_epoch: float = 0.0
        self._last_query_url: Optional[str] = None

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="geoint-copernicus",
            name="Copernicus Open Access Hub (ESA Sentinel)",
            category=ProviderCategory.GEOINT,
            tier=ProviderTier.FREE,
            base_url="https://catalogue.dataspace.copernicus.eu",
            auth_type="oauth2",
            rate_limit_rpm=30,
            supported_schemas=["NormalizedGeoObservation"],
            required_env_vars=["COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET"],
            description=(
                "Free Sentinel-1 SAR, Sentinel-2 multispectral, Sentinel-3 ocean, "
                "Sentinel-5P atmospheric satellite data from ESA."
            ),
            docs_url="https://documentation.dataspace.copernicus.eu/APIs/OData.html",
            airgap_capable=True,
            enabled=True,
            tags=["sar", "optical", "satellite", "free", "sentinel", "esa"],
        )

    def validate_credentials(self) -> bool:
        if self._is_airgapped():
            return self._has_airgapped_cache()

        client_id = self._get_secret("COPERNICUS_CLIENT_ID")
        client_secret = self._get_secret("COPERNICUS_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.warning("Copernicus credentials missing from environment secrets.")
            return False

        token = self._get_token()
        return bool(token)

    def _get_token(self) -> Optional[str]:
        now = time.time()
        if self._token and now < self._token_expiry_epoch:
            return self._token

        client_id = self._get_secret("COPERNICUS_CLIENT_ID")
        client_secret = self._get_secret("COPERNICUS_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None

        try:
            token_response = self.client.post_form_json(
                self.config.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
        except Exception as exc:  # pragma: no cover - network guarded by tests via mocks
            logger.error("Copernicus token request failed: %s", exc.__class__.__name__)
            return None

        access_token = token_response.get("access_token")
        if not access_token:
            logger.error("Copernicus token response missing access_token.")
            return None

        expires_in = token_response.get("expires_in", 600)
        try:
            expires_seconds = int(expires_in)
        except (TypeError, ValueError):
            expires_seconds = 600
        # Safety margin to avoid edge-of-expiry failures during tactical pulls.
        self._token_expiry_epoch = time.time() + max(30, expires_seconds - 30)
        self._token = str(access_token)
        return self._token

    def fetch(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        effective = {
            "collection": self.config.default_collection,
            "product_type": self.config.default_product_type,
            "aoi": "persian_gulf",
            "days_back": 7,
            "max_results": self.config.max_results,
        }
        if params:
            effective.update(params)

        if self._is_airgapped():
            cached = self._read_latest_cached_search()
            if cached is None:
                return {
                    "products": [],
                    "total_results": 0,
                    "note": "No cached data available in airgapped mode",
                }
            return cached

        token = self._get_token()
        if not token:
            return {"products": [], "total_results": 0, "error": "authentication_failed"}

        query_url = self._build_odata_url(effective)
        self._last_query_url = query_url
        headers = {"Authorization": f"Bearer {token}"}
        payload = self.client.get_json(query_url, headers=headers)
        products = list(payload.get("value") or [])

        cached_path = self._cache_search_payload(payload)
        enriched_products = []
        for product in products:
            copy_item = dict(product)
            copy_item["_aoi_name"] = effective.get("aoi")
            copy_item["_raw_data_ref"] = str(cached_path) if cached_path else None
            enriched_products.append(copy_item)

        return {
            "products": enriched_products,
            "total_results": len(enriched_products),
            "query": query_url,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_sentinel1_sar(
        self, aoi: str = "persian_gulf", days_back: int = 7, product_type: str = "GRD"
    ) -> Dict[str, Any]:
        return self.fetch(
            {
                "collection": "SENTINEL-1",
                "product_type": product_type,
                "aoi": aoi,
                "days_back": days_back,
                "max_results": self.config.max_results,
            }
        )

    def fetch_sentinel2_optical(
        self, aoi: str = "full_saudi", days_back: int = 7, max_cloud_cover: float = 30.0
    ) -> Dict[str, Any]:
        return self.fetch(
            {
                "collection": "SENTINEL-2",
                "product_type": "S2MSI2A",
                "aoi": aoi,
                "days_back": days_back,
                "max_results": self.config.max_results,
                "max_cloud_cover": max_cloud_cover,
            }
        )

    def fetch_sentinel5p_atmosphere(self, aoi: str = "full_saudi", days_back: int = 3) -> Dict[str, Any]:
        return self.fetch(
            {
                "collection": "SENTINEL-5P",
                "product_type": "L2",
                "aoi": aoi,
                "days_back": days_back,
                "max_results": self.config.max_results,
            }
        )

    def normalize(self, raw_data: Dict[str, Any]) -> List[NormalizedGeoObservation]:
        products = list(raw_data.get("products") or raw_data.get("value") or [])
        return self.normalizer.normalize_batch(products)

    def health_check(self) -> Dict[str, Any]:
        started = time.time()
        if self._is_airgapped():
            cache_dir = self._cache_root()
            if not cache_dir.exists():
                return {"status": "OFFLINE", "mode": "AIRGAPPED", "detail": "No cache directory"}

            json_files = sorted(cache_dir.glob("**/search_*.json"))
            if not json_files:
                return {"status": "OFFLINE", "mode": "AIRGAPPED", "detail": "No cached data files"}

            newest = max(json_files, key=lambda p: p.stat().st_mtime)
            newest_age_days = (time.time() - newest.stat().st_mtime) / 86400.0
            status = "OK" if newest_age_days <= 7 else "DEGRADED"
            total_size = sum(path.stat().st_size for path in json_files)
            return {
                "status": status,
                "mode": "AIRGAPPED",
                "cache_file_count": len(json_files),
                "latest_file": str(newest),
                "latest_age_days": round(newest_age_days, 2),
                "cache_size_bytes": total_size,
                "latency_ms": int((time.time() - started) * 1000),
            }

        token = self._get_token()
        if not token:
            return {
                "status": "ERROR",
                "mode": "ONLINE",
                "detail": "Token refresh failed",
                "latency_ms": int((time.time() - started) * 1000),
            }

        try:
            search = self.fetch({"max_results": 1, "days_back": 1, "aoi": "full_saudi"})
            return {
                "status": "OK",
                "mode": "ONLINE",
                "results_sampled": search.get("total_results", 0),
                "latency_ms": int((time.time() - started) * 1000),
            }
        except Exception as exc:  # pragma: no cover - exercised by integration environments
            return {
                "status": "ERROR",
                "mode": "ONLINE",
                "detail": f"Search failed: {exc.__class__.__name__}",
                "latency_ms": int((time.time() - started) * 1000),
            }

    def _build_odata_url(self, params: Dict[str, Any]) -> str:
        collection = str(params.get("collection", self.config.default_collection))
        product_type = str(params.get("product_type", self.config.default_product_type))
        max_results = int(params.get("max_results", self.config.max_results))
        days_back = int(params.get("days_back", 7))
        aoi_key = str(params.get("aoi", "persian_gulf"))
        aoi_wkt = self.config.saudi_aoi.get(aoi_key, self.config.saudi_aoi["persian_gulf"])
        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        filters: List[str] = [f"Collection/Name eq '{collection}'"]
        if product_type:
            filters.append(
                "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq "
                f"'productType' and att/OData.CSC.StringAttribute/Value eq '{product_type}')"
            )
        filters.append(f"ContentDate/Start gt {start_date}T00:00:00.000Z")
        filters.append(f"OData.CSC.Intersects(area=geography'SRID=4326;{aoi_wkt}')")

        max_cloud_cover = params.get("max_cloud_cover")
        if max_cloud_cover is not None:
            filters.append(
                "Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' "
                f"and att/OData.CSC.DoubleAttribute/Value lt {float(max_cloud_cover)})"
            )

        filter_expr = " and ".join(filters)
        encoded_filter = quote(filter_expr, safe="()/$;=,:'.")
        return (
            f"{self.config.odata_url}/Products?$filter={encoded_filter}"
            f"&$top={max_results}&$orderby=ContentDate/Start desc"
        )

    def _cache_root(self) -> Path:
        return Path("data") / "integrations" / "geoint-copernicus"

    def _cache_search_payload(self, payload: Dict[str, Any]) -> Optional[Path]:
        now = datetime.now(timezone.utc)
        date_dir = self._cache_root() / now.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        cache_path = date_dir / f"search_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return cache_path

    def _read_latest_cached_search(self) -> Optional[Dict[str, Any]]:
        root = self._cache_root()
        if not root.exists():
            return None
        candidates = sorted(root.glob("**/search_*.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        with latest.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        products = list(payload.get("value") or payload.get("products") or [])
        return {
            "products": products,
            "total_results": len(products),
            "query": "airgapped-cache",
            "cached_at": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat(),
        }

    def _is_airgapped(self) -> bool:
        value = os.getenv("S3M_AIRGAPPED", "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _has_airgapped_cache(self) -> bool:
        root = self._cache_root()
        if not root.exists():
            return False
        return any(path.is_file() for path in root.glob("**/*"))

    def _get_secret(self, key: str) -> Optional[str]:
        direct = self.secret_provider.get_secret(key)
        if direct:
            return direct
        return self.secret_provider.get_secret(f"S3M_{key}")

    @property
    def last_query_url(self) -> Optional[str]:
        return self._last_query_url


# Best-effort registration into framework registry when available.
try:
    ProviderRegistry.register(CopernicusAdapter)
except Exception:  # pragma: no cover - safe no-op if registry unavailable
    logger.debug("ProviderRegistry registration skipped for CopernicusAdapter.")
