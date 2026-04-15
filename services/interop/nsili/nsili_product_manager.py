"""NSILI product ingestion and serving manager for S3M ISR outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib import error, request

from services.interop.nsili.nsili_catalog import NSILICatalog
from src.apps.intel.models import ReportType


class NSILIProductManager:
    """Map S3M intelligence products into NSILI catalog entries."""

    def __init__(self, catalog: NSILICatalog) -> None:
        if not isinstance(catalog, NSILICatalog):
            raise ValueError("catalog must be an NSILICatalog instance")
        self.catalog = catalog

    def ingest_intel_product(self, intel_product: dict) -> str:
        """
        Convert one S3M intelligence product to NSILI metadata and register it.

        Required mapping:
        - ReportType.INTSUM -> REPORT
        - ReportType.DAILY_BRIEF -> REPORT
        - Satellite imagery -> IMAGERY
        - Drone FMV -> VIDEO
        """
        if not isinstance(intel_product, dict):
            raise ValueError("intel_product must be a dictionary")

        nsili_product: dict[str, Any] = {
            "productId": self._resolve_product_id(intel_product),
            "productType": self._infer_product_type(intel_product),
            "dateCreated": (
                intel_product.get("dateCreated")
                or intel_product.get("created_at")
                or intel_product.get("timestamp")
            ),
            "classification": intel_product.get("classification"),
            "spatialCoverage": (
                intel_product.get("spatialCoverage")
                or intel_product.get("bbox")
                or intel_product.get("spatial_coverage")
            ),
            "creator": (
                intel_product.get("creator")
                or intel_product.get("originator")
                or intel_product.get("source_id")
                or "S3M"
            ),
            "title": (
                intel_product.get("title")
                or intel_product.get("name")
                or intel_product.get("report_id")
                or "S3M ISR Product"
            ),
            "format": self._resolve_format(intel_product),
        }

        content = self._extract_content(intel_product)
        if content is not None:
            nsili_product["content"] = content
        content_ref = intel_product.get("contentRef")
        if isinstance(content_ref, str) and content_ref.strip():
            nsili_product["contentRef"] = content_ref.strip()

        return self.catalog.register_product(nsili_product)

    def serve_product(self, product_id: str) -> bytes:
        """Retrieve one product payload for coalition partner requests."""
        return self.catalog.read_product_content(product_id)

    def sync_from_partner(self, partner_url: str) -> int:
        """
        Import catalog entries from partner NSILI XML.

        Phase 1 behavior: best-effort pull and local registration.
        Standing queries and advanced reconciliation are Phase 2.
        """
        url_text = str(partner_url or "").strip()
        if not url_text:
            raise ValueError("partner_url is required")

        try:
            xml_payload = self._read_partner_catalog(url_text)
        except (ValueError, OSError, error.URLError, TimeoutError):
            return 0

        entries = self.catalog.from_nsili_xml(xml_payload)
        imported = 0
        for row in entries:
            product_id = str(row.get("productId", "")).strip()
            if not product_id or self.catalog.has_product(product_id):
                continue
            self.catalog.register_product(row)
            imported += 1
        return imported

    def export_catalog_xml(self) -> str:
        """Export full local NSILI catalog as XML for offline transfer."""
        return self.catalog.to_nsili_xml(self.catalog.list_products(limit=self.catalog.max_products))

    def _resolve_product_id(self, intel_product: dict[str, Any]) -> str:
        for key in ("productId", "report_id", "id", "item_id"):
            value = intel_product.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise ValueError("intel_product must include a stable identifier")

    def _infer_product_type(self, intel_product: dict[str, Any]) -> str:
        report_type = intel_product.get("report_type")
        report_type_text = (
            report_type.value if isinstance(report_type, ReportType) else str(report_type or "")
        ).strip()

        mapped_report_type = {
            ReportType.INTSUM.value: "REPORT",
            ReportType.DAILY_BRIEF.value: "REPORT",
        }.get(report_type_text)
        if mapped_report_type:
            return mapped_report_type

        media_hint = " ".join(
            str(intel_product.get(key, "")).lower()
            for key in ("media_type", "sensor_type", "type", "platform", "title")
        )
        format_hint = str(intel_product.get("format", "")).lower()
        if any(token in media_hint for token in ("satellite", "imagery", "image")) or format_hint.startswith(
            "image/"
        ):
            return "IMAGERY"
        if any(token in media_hint for token in ("drone", "fmv", "video")) or format_hint.startswith("video/"):
            return "VIDEO"
        return "REPORT"

    def _resolve_format(self, intel_product: dict[str, Any]) -> str:
        value = str(intel_product.get("format", "")).strip()
        if value:
            return value
        if isinstance(intel_product.get("content"), (dict, list)):
            return "application/json"
        if isinstance(intel_product.get("content"), bytes):
            return "application/octet-stream"
        return "text/plain"

    def _extract_content(self, intel_product: dict[str, Any]) -> Any:
        if "content" in intel_product:
            return intel_product.get("content")

        assembled = {}
        for field in ("body_en", "body_ar", "summary_en", "summary_ar"):
            value = intel_product.get(field)
            if isinstance(value, str) and value.strip():
                assembled[field] = value
        if assembled:
            return assembled
        return None

    def _read_partner_catalog(self, partner_url: str) -> str:
        if partner_url.startswith(("http://", "https://")):
            req = request.Request(
                url=partner_url,
                method="GET",
                headers={"Accept": "application/xml, text/xml"},
            )
            with request.urlopen(req, timeout=6.0) as response:
                return response.read().decode("utf-8", errors="ignore")

        # Tactical context: air-gapped exchanges can arrive as removable-media files.
        path = Path(partner_url)
        if not path.exists() or not path.is_file():
            raise ValueError(f"Partner catalog not found: {partner_url}")
        return path.read_text(encoding="utf-8")
