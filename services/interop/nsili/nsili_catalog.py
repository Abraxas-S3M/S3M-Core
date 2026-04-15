"""Local STANAG 4559 Ed.3 catalog storage and query helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import xml.etree.ElementTree as ET
from uuid import uuid4


NSILI_NAMESPACE = "urn:nato:stanag:4559:ed3"
ALLOWED_PRODUCT_TYPES = {"INTSUM", "IMAGERY", "VIDEO", "REPORT"}
ALLOWED_CLASSIFICATIONS = {
    "UNCLASSIFIED",
    "FOUO",
    "CONFIDENTIAL",
    "SECRET",
    "TOP_SECRET",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return _utc_now_iso()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


class NSILICatalog:
    """Air-gapped NSILI catalog backed by local JSON files."""

    def __init__(self, config: dict) -> None:
        if not isinstance(config, dict):
            raise ValueError("config must be a dictionary")

        self.catalog_dir = Path(str(config.get("catalog_dir", "data/interop/nsili_catalog/"))).resolve()
        self.max_products = max(1, int(config.get("max_products", 10000)))
        self.default_classification = str(
            config.get("default_classification", "UNCLASSIFIED")
        ).strip().upper() or "UNCLASSIFIED"

        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        self.products_dir = self.catalog_dir / "products"
        self.products_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_index_path = self.catalog_dir / "catalog.json"
        self._products: dict[str, dict[str, Any]] = {}
        self._load()

    def register_product(self, product: dict) -> str:
        """Register one product in the local NSILI catalog."""
        if not isinstance(product, dict):
            raise ValueError("product must be a dictionary")

        payload = self._normalize_product(product)
        product_id = payload["productId"]
        is_new = product_id not in self._products
        if is_new and len(self._products) >= self.max_products:
            raise ValueError(f"max_products limit reached ({self.max_products})")

        self._products[product_id] = payload
        self._save()
        return product_id

    def query(
        self,
        product_type: str = None,
        time_range: tuple = None,
        bbox: tuple = None,
        classification: str = None,
    ) -> list[dict]:
        """Search products by NSILI metadata filters."""
        wanted_type = str(product_type or "").strip().upper() or None
        wanted_classification = str(classification or "").strip().upper() or None
        wanted_bbox = self._normalize_bbox(bbox) if bbox is not None else None
        start_dt: datetime | None = None
        end_dt: datetime | None = None
        if time_range is not None:
            if not isinstance(time_range, tuple) or len(time_range) != 2:
                raise ValueError("time_range must be a tuple(start, end)")
            start_dt = _parse_datetime(time_range[0])
            end_dt = _parse_datetime(time_range[1])

        rows: list[dict[str, Any]] = []
        for product in self._products.values():
            if wanted_type and str(product.get("productType", "")).upper() != wanted_type:
                continue
            if wanted_classification and str(product.get("classification", "")).upper() != wanted_classification:
                continue

            created_at = _parse_datetime(str(product.get("dateCreated", "")))
            if start_dt and (created_at is None or created_at < start_dt):
                continue
            if end_dt and (created_at is None or created_at > end_dt):
                continue

            product_bbox = self._normalize_bbox(product.get("spatialCoverage"))
            if wanted_bbox and (product_bbox is None or not self._bbox_intersects(product_bbox, wanted_bbox)):
                continue

            rows.append(dict(product))

        rows.sort(key=lambda row: str(row.get("dateCreated", "")), reverse=True)
        return rows

    def get_product(self, product_id: str) -> dict:
        """Return one product metadata row by ID."""
        pid = str(product_id).strip()
        if not pid:
            raise ValueError("product_id is required")
        product = self._products.get(pid)
        if product is None:
            raise KeyError(f"Unknown product_id: {pid}")
        return dict(product)

    def has_product(self, product_id: str) -> bool:
        """Check if product exists in local catalog."""
        return str(product_id).strip() in self._products

    def list_products(self, limit: int = 100) -> list[dict]:
        """List up to `limit` catalog entries."""
        max_rows = max(1, int(limit))
        rows = sorted(
            (dict(item) for item in self._products.values()),
            key=lambda row: str(row.get("dateCreated", "")),
            reverse=True,
        )
        return rows[:max_rows]

    def delete_product(self, product_id: str) -> bool:
        """Delete one product and its local content payload (if present)."""
        pid = str(product_id).strip()
        if not pid:
            raise ValueError("product_id is required")
        payload = self._products.pop(pid, None)
        if payload is None:
            return False

        content_ref = payload.get("contentRef")
        if isinstance(content_ref, str) and content_ref.strip():
            path = self._resolve_content_path(content_ref)
            if path is not None and path.exists():
                path.unlink(missing_ok=True)

        self._save()
        return True

    def to_nsili_xml(self, products: list[dict]) -> str:
        """Serialize products to a compact NSILI-style XML payload."""
        if not isinstance(products, list):
            raise ValueError("products must be a list")

        ET.register_namespace("", NSILI_NAMESPACE)
        root = ET.Element(f"{{{NSILI_NAMESPACE}}}CatalogResponse")
        for row in products:
            if not isinstance(row, dict):
                continue
            product_el = ET.SubElement(root, f"{{{NSILI_NAMESPACE}}}Product")
            for key in ("productId", "productType", "dateCreated", "classification", "creator", "title", "format"):
                value = str(row.get(key, "")).strip()
                child = ET.SubElement(product_el, f"{{{NSILI_NAMESPACE}}}{key}")
                child.text = value

            spatial = self._normalize_bbox(row.get("spatialCoverage"))
            if spatial is not None:
                spatial_el = ET.SubElement(product_el, f"{{{NSILI_NAMESPACE}}}spatialCoverage")
                for name, value in (
                    ("minLat", spatial[0]),
                    ("minLon", spatial[1]),
                    ("maxLat", spatial[2]),
                    ("maxLon", spatial[3]),
                ):
                    coord = ET.SubElement(spatial_el, f"{{{NSILI_NAMESPACE}}}{name}")
                    coord.text = f"{value:.6f}"

            content_ref = str(row.get("contentRef", "")).strip()
            if content_ref:
                cref = ET.SubElement(product_el, f"{{{NSILI_NAMESPACE}}}contentRef")
                cref.text = content_ref

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def from_nsili_xml(self, xml_str: str) -> list[dict]:
        """Parse NSILI XML product rows into dictionaries."""
        if not isinstance(xml_str, str) or not xml_str.strip():
            return []

        root = ET.fromstring(xml_str)
        rows: list[dict[str, Any]] = []
        for node in root.iter():
            if _local_name(node.tag) != "Product":
                continue

            row: dict[str, Any] = {
                "productId": "",
                "productType": "REPORT",
                "dateCreated": _utc_now_iso(),
                "classification": self.default_classification,
                "creator": "",
                "title": "",
                "format": "application/octet-stream",
            }
            for child in list(node):
                key = _local_name(child.tag)
                text = str(child.text or "").strip()
                if key == "spatialCoverage":
                    row["spatialCoverage"] = self._extract_xml_bbox(child)
                elif key in {
                    "productId",
                    "productType",
                    "dateCreated",
                    "classification",
                    "creator",
                    "title",
                    "format",
                    "contentRef",
                }:
                    row[key] = text

            row["productType"] = self._normalize_product_type(str(row.get("productType", "REPORT")))
            row["classification"] = self._normalize_classification(str(row.get("classification", "")))
            row["dateCreated"] = _format_datetime(_parse_datetime(str(row.get("dateCreated", ""))))
            rows.append(row)
        return rows

    def read_product_content(self, product_id: str) -> bytes:
        """Read persisted content payload for one product ID."""
        product = self.get_product(product_id)
        content_ref = str(product.get("contentRef", "")).strip()
        if not content_ref:
            return b""
        path = self._resolve_content_path(content_ref)
        if path is None or not path.exists() or not path.is_file():
            return b""
        return path.read_bytes()

    def _load(self) -> None:
        if not self._catalog_index_path.exists():
            self._products = {}
            return

        try:
            payload = json.loads(self._catalog_index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._products = {}
            return

        rows = payload.get("products", []) if isinstance(payload, dict) else []
        parsed: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = self._normalize_product(row, persist_content=False)
            parsed[normalized["productId"]] = normalized
        self._products = parsed

    def _save(self) -> None:
        payload = {"products": list(self._products.values())}
        # Tactical context: atomic writes avoid catalog corruption during power loss.
        with NamedTemporaryFile("w", encoding="utf-8", dir=str(self.catalog_dir), delete=False) as temp_file:
            json.dump(payload, temp_file, ensure_ascii=True)
            temp_path = Path(temp_file.name)
        temp_path.replace(self._catalog_index_path)

    def _normalize_product(self, product: dict[str, Any], persist_content: bool = True) -> dict[str, Any]:
        product_id = str(product.get("productId") or product.get("id") or f"nsili-{uuid4().hex[:12]}").strip()
        if not product_id:
            raise ValueError("productId is required")

        product_type = self._normalize_product_type(str(product.get("productType", "REPORT")))
        classification = self._normalize_classification(str(product.get("classification", self.default_classification)))
        date_created = _format_datetime(
            _parse_datetime(
                str(
                    product.get("dateCreated")
                    or product.get("created_at")
                    or product.get("timestamp")
                    or _utc_now_iso()
                )
            )
        )
        spatial = self._normalize_bbox(product.get("spatialCoverage") or product.get("bbox"))
        creator = str(product.get("creator") or product.get("originator") or "").strip()
        title = str(product.get("title") or product.get("name") or product_id).strip()
        data_format = str(product.get("format") or product.get("mime_type") or "application/octet-stream").strip()

        content_ref = str(product.get("contentRef", "")).strip()
        if persist_content:
            stored_ref = self._persist_content(product_id, product)
            if stored_ref:
                content_ref = stored_ref

        payload: dict[str, Any] = {
            "productId": product_id,
            "productType": product_type,
            "dateCreated": date_created,
            "classification": classification,
            "spatialCoverage": spatial,
            "creator": creator,
            "title": title,
            "format": data_format,
        }
        if content_ref:
            payload["contentRef"] = content_ref
        return payload

    def _persist_content(self, product_id: str, product: dict[str, Any]) -> str | None:
        content = product.get("content")
        if content is None:
            report_fields = {}
            for field in ("body_en", "body_ar", "summary_en", "summary_ar", "content_text"):
                value = product.get(field)
                if isinstance(value, str) and value.strip():
                    report_fields[field] = value
            if report_fields:
                content = report_fields
            elif isinstance(product.get("contentRef"), str) and str(product.get("contentRef")).strip():
                return str(product.get("contentRef")).strip()
            else:
                return None

        stem = f"{product_id}-{uuid4().hex[:6]}"
        if isinstance(content, bytes):
            path = self.products_dir / f"{stem}.bin"
            path.write_bytes(content)
        elif isinstance(content, (dict, list)):
            path = self.products_dir / f"{stem}.json"
            path.write_text(json.dumps(content, ensure_ascii=True), encoding="utf-8")
        else:
            path = self.products_dir / f"{stem}.txt"
            path.write_text(str(content), encoding="utf-8")
        return str(path.relative_to(self.catalog_dir))

    def _normalize_product_type(self, product_type: str) -> str:
        value = str(product_type).strip().upper()
        if not value:
            return "REPORT"
        if value in ALLOWED_PRODUCT_TYPES:
            return value
        return "REPORT"

    def _normalize_classification(self, classification: str) -> str:
        value = str(classification).strip().upper().replace(" ", "_")
        if not value:
            return self.default_classification
        if value in ALLOWED_CLASSIFICATIONS:
            return value
        return value

    def _normalize_bbox(self, bbox: Any) -> tuple[float, float, float, float] | None:
        if bbox is None:
            return None

        values: list[float]
        if isinstance(bbox, (tuple, list)) and len(bbox) == 4:
            values = [float(part) for part in bbox]
        elif isinstance(bbox, dict):
            keys = ("minLat", "minLon", "maxLat", "maxLon")
            if not all(key in bbox for key in keys):
                return None
            values = [float(bbox[key]) for key in keys]
        else:
            return None

        min_lat, min_lon, max_lat, max_lon = values
        if min_lat > max_lat:
            min_lat, max_lat = max_lat, min_lat
        if min_lon > max_lon:
            min_lon, max_lon = max_lon, min_lon

        if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
            raise ValueError("Latitude values must be between -90 and 90")
        if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
            raise ValueError("Longitude values must be between -180 and 180")
        return (min_lat, min_lon, max_lat, max_lon)

    @staticmethod
    def _bbox_intersects(
        left: tuple[float, float, float, float], right: tuple[float, float, float, float]
    ) -> bool:
        return not (
            left[2] < right[0]
            or right[2] < left[0]
            or left[3] < right[1]
            or right[3] < left[1]
        )

    def _extract_xml_bbox(self, node: ET.Element) -> tuple[float, float, float, float] | None:
        coords: dict[str, float] = {}
        for child in list(node):
            name = _local_name(child.tag)
            if name not in {"minLat", "minLon", "maxLat", "maxLon"}:
                continue
            text = str(child.text or "").strip()
            if not text:
                continue
            try:
                coords[name] = float(text)
            except ValueError:
                continue
        if {"minLat", "minLon", "maxLat", "maxLon"} - set(coords):
            return None
        return self._normalize_bbox(coords)

    def _resolve_content_path(self, content_ref: str) -> Path | None:
        ref = str(content_ref).strip()
        if not ref:
            return None
        path = (self.catalog_dir / ref).resolve()
        if self.catalog_dir not in path.parents and path != self.catalog_dir:
            return None
        return path
