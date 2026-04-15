"""OGC WFS client for coalition feature exchange."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request
import xml.etree.ElementTree as ET


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class _WFSHTTPResult:
    body: bytes
    content_type: str


class WFSClient:
    """Retrieve feature capabilities and vector data from WFS servers."""

    def __init__(self, base_url: str) -> None:
        self.base_url = str(base_url or "").strip()
        if not self.base_url:
            raise ValueError("base_url is required")
        self.base_url = self.base_url.rstrip("?")
        self.timeout = 8.0
        self._last_capabilities: dict[str, Any] | None = None

    def get_capabilities(self) -> dict:
        """Fetch and parse WFS GetCapabilities metadata."""
        params = {
            "SERVICE": "WFS",
            "REQUEST": "GetCapabilities",
        }
        try:
            response = self._http_get(params)
            root = ET.fromstring(response.body)
            parsed = self._parse_capabilities(root)
            parsed["online"] = True
            self._last_capabilities = parsed
            return parsed
        except (ET.ParseError, error.URLError, error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            fallback = {
                "service": "WFS",
                "version": "",
                "title": "",
                "abstract": "",
                "feature_types": [],
                "online": False,
                "error": str(exc),
            }
            self._last_capabilities = fallback
            return fallback

    def get_feature(self, type_name: str, bbox: tuple = None, max_features: int = 100) -> str:
        """Request feature payload from a WFS server in GML or GeoJSON."""
        type_name_value = str(type_name or "").strip()
        if not type_name_value:
            raise ValueError("type_name is required")

        feature_limit = int(max_features)
        if feature_limit <= 0:
            raise ValueError("max_features must be greater than zero")
        if feature_limit > 5000:
            raise ValueError("max_features must not exceed 5000")

        params: dict[str, str] = {
            "SERVICE": "WFS",
            "REQUEST": "GetFeature",
            "VERSION": "2.0.0",
            "TYPENAMES": type_name_value,
            "COUNT": str(feature_limit),
        }
        if bbox is not None:
            bbox_tuple = self._validate_bbox(bbox)
            # Tactical context: explicit AOI bounding limits avoid over-collection
            # and preserve bandwidth on constrained coalition links.
            params["BBOX"] = ",".join(str(value) for value in bbox_tuple) + ",EPSG:4326"

        try:
            response = self._http_get(params)
            return response.body.decode("utf-8", errors="ignore")
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            return ""

    def list_feature_types(self) -> list[dict]:
        """Return available feature type descriptors."""
        if self._last_capabilities is None or not self._last_capabilities.get("feature_types"):
            self.get_capabilities()
        if not isinstance(self._last_capabilities, dict):
            return []
        feature_types = self._last_capabilities.get("feature_types", [])
        return [item for item in feature_types if isinstance(item, dict)]

    def _http_get(self, params: dict[str, str]) -> _WFSHTTPResult:
        query = parse.urlencode(params)
        delimiter = "&" if "?" in self.base_url else "?"
        url = f"{self.base_url}{delimiter}{query}"
        req = request.Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": "S3M-OGC-WFSClient/1.0",
                "Accept": "*/*",
            },
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            return _WFSHTTPResult(
                body=response.read(),
                content_type=str(response.headers.get("Content-Type", "")).strip(),
            )

    def _parse_capabilities(self, root: ET.Element) -> dict[str, Any]:
        title = ""
        abstract = ""
        version = str(root.attrib.get("version", "")).strip()

        for elem in root.iter():
            name = _local_name(elem.tag)
            if name in {"ServiceIdentification", "Service"}:
                for child in list(elem):
                    child_name = _local_name(child.tag)
                    if child_name == "Title" and not title:
                        title = str(child.text or "").strip()
                    elif child_name == "Abstract" and not abstract:
                        abstract = str(child.text or "").strip()
                if title or abstract:
                    break

        feature_types: list[dict[str, Any]] = []
        for elem in root.iter():
            if _local_name(elem.tag) != "FeatureType":
                continue
            name_value = ""
            title_value = ""
            abstract_value = ""
            default_crs = ""
            wgs84_bbox: tuple[float, float, float, float] | None = None
            for child in list(elem):
                child_name = _local_name(child.tag)
                if child_name == "Name":
                    name_value = str(child.text or "").strip()
                elif child_name == "Title":
                    title_value = str(child.text or "").strip()
                elif child_name == "Abstract":
                    abstract_value = str(child.text or "").strip()
                elif child_name in {"DefaultCRS", "DefaultSRS"}:
                    default_crs = str(child.text or "").strip()
                elif child_name == "WGS84BoundingBox":
                    lower = upper = None
                    for bbox_child in list(child):
                        bbox_name = _local_name(bbox_child.tag)
                        text = str(bbox_child.text or "").strip()
                        if bbox_name == "LowerCorner":
                            lower = text
                        elif bbox_name == "UpperCorner":
                            upper = text
                    if lower and upper:
                        lower_parts = lower.split()
                        upper_parts = upper.split()
                        if len(lower_parts) >= 2 and len(upper_parts) >= 2:
                            minx = _as_float(lower_parts[0])
                            miny = _as_float(lower_parts[1])
                            maxx = _as_float(upper_parts[0])
                            maxy = _as_float(upper_parts[1])
                            wgs84_bbox = (minx, miny, maxx, maxy)

            if name_value:
                feature_types.append(
                    {
                        "name": name_value,
                        "title": title_value,
                        "abstract": abstract_value,
                        "default_crs": default_crs,
                        "bbox": wgs84_bbox,
                    }
                )

        return {
            "service": "WFS",
            "version": version,
            "title": title,
            "abstract": abstract,
            "feature_types": feature_types,
        }

    @staticmethod
    def _validate_bbox(bbox: tuple) -> tuple[float, float, float, float]:
        if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
            raise ValueError("bbox must contain four values (minx, miny, maxx, maxy)")
        minx, miny, maxx, maxy = (float(value) for value in bbox)
        if maxx <= minx or maxy <= miny:
            raise ValueError("bbox max values must be greater than min values")
        return minx, miny, maxx, maxy
