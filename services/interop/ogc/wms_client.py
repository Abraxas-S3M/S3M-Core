"""OGC WMS client for coalition raster map interoperability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request
import xml.etree.ElementTree as ET


def _local_name(tag: str) -> str:
    """Return the XML local name without namespace prefixes."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class _HTTPRequestResult:
    body: bytes
    content_type: str


class WMSClient:
    """Retrieve map capabilities and rendered layers from WMS servers."""

    def __init__(self, base_url: str) -> None:
        self.base_url = str(base_url or "").strip()
        if not self.base_url:
            raise ValueError("base_url is required")
        self.base_url = self.base_url.rstrip("?")
        self.timeout = 8.0
        self._last_capabilities: dict[str, Any] | None = None

    def get_capabilities(self) -> dict:
        """Fetch and parse WMS GetCapabilities metadata."""
        params = {
            "SERVICE": "WMS",
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
            # Tactical context: disconnected coalition links must degrade gracefully
            # so COP rendering can fall back to cached or alternate layers.
            fallback = {
                "service": "WMS",
                "version": "",
                "title": "",
                "abstract": "",
                "layers": [],
                "online": False,
                "error": str(exc),
            }
            self._last_capabilities = fallback
            return fallback

    def get_map(
        self,
        layers: list[str],
        bbox: tuple,
        width: int,
        height: int,
        srs: str = "EPSG:4326",
        format: str = "image/png",
    ) -> bytes:
        """Request a rendered map image for the selected layers."""
        layer_names = [str(layer).strip() for layer in layers if str(layer).strip()]
        if not layer_names:
            raise ValueError("layers must contain at least one layer name")
        bbox_tuple = self._validate_bbox(bbox)
        width_px = int(width)
        height_px = int(height)
        if width_px <= 0 or height_px <= 0:
            raise ValueError("width and height must be greater than zero")
        if width_px > 8192 or height_px > 8192:
            raise ValueError("width and height must not exceed 8192 pixels")
        srs_value = str(srs or "EPSG:4326").strip() or "EPSG:4326"
        format_value = str(format or "image/png").strip() or "image/png"

        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": ",".join(layer_names),
            "STYLES": "",
            "BBOX": ",".join(str(value) for value in bbox_tuple),
            "WIDTH": str(width_px),
            "HEIGHT": str(height_px),
            "CRS": srs_value,
            "FORMAT": format_value,
            "TRANSPARENT": "TRUE",
        }

        try:
            response = self._http_get(params)
            return response.body
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            return b""

    def get_available_layers(self) -> list[dict]:
        """Return flattened list of available WMS layers."""
        if self._last_capabilities is None or not self._last_capabilities.get("layers"):
            self.get_capabilities()
        if not isinstance(self._last_capabilities, dict):
            return []
        layers = self._last_capabilities.get("layers", [])
        return [layer for layer in layers if isinstance(layer, dict)]

    def _http_get(self, params: dict[str, str]) -> _HTTPRequestResult:
        query = parse.urlencode(params)
        delimiter = "&" if "?" in self.base_url else "?"
        url = f"{self.base_url}{delimiter}{query}"
        req = request.Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": "S3M-OGC-WMSClient/1.0",
                "Accept": "*/*",
            },
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            content_type = str(response.headers.get("Content-Type", "")).strip()
            return _HTTPRequestResult(body=response.read(), content_type=content_type)

    def _parse_capabilities(self, root: ET.Element) -> dict[str, Any]:
        service_title = ""
        service_abstract = ""
        version = str(root.attrib.get("version", "")).strip()

        for elem in root.iter():
            name = _local_name(elem.tag)
            if name == "Service":
                for child in list(elem):
                    child_name = _local_name(child.tag)
                    if child_name == "Title":
                        service_title = str(child.text or "").strip()
                    elif child_name == "Abstract":
                        service_abstract = str(child.text or "").strip()
                break

        layers: list[dict[str, Any]] = []
        for layer_elem in root.iter():
            if _local_name(layer_elem.tag) != "Layer":
                continue
            layer_name = ""
            layer_title = ""
            layer_abstract = ""
            crs_values: list[str] = []
            bbox: tuple[float, float, float, float] | None = None

            for child in list(layer_elem):
                child_name = _local_name(child.tag)
                if child_name == "Name":
                    layer_name = str(child.text or "").strip()
                elif child_name == "Title":
                    layer_title = str(child.text or "").strip()
                elif child_name == "Abstract":
                    layer_abstract = str(child.text or "").strip()
                elif child_name in {"CRS", "SRS"}:
                    crs = str(child.text or "").strip()
                    if crs and crs not in crs_values:
                        crs_values.append(crs)
                elif child_name == "EX_GeographicBoundingBox":
                    west = east = south = north = 0.0
                    for bbox_child in list(child):
                        bbox_child_name = _local_name(bbox_child.tag)
                        if bbox_child_name == "westBoundLongitude":
                            west = _as_float(bbox_child.text)
                        elif bbox_child_name == "eastBoundLongitude":
                            east = _as_float(bbox_child.text)
                        elif bbox_child_name == "southBoundLatitude":
                            south = _as_float(bbox_child.text)
                        elif bbox_child_name == "northBoundLatitude":
                            north = _as_float(bbox_child.text)
                    bbox = (west, south, east, north)
                elif child_name == "LatLonBoundingBox":
                    minx = _as_float(child.attrib.get("minx"))
                    miny = _as_float(child.attrib.get("miny"))
                    maxx = _as_float(child.attrib.get("maxx"))
                    maxy = _as_float(child.attrib.get("maxy"))
                    bbox = (minx, miny, maxx, maxy)

            if layer_name:
                layers.append(
                    {
                        "name": layer_name,
                        "title": layer_title,
                        "abstract": layer_abstract,
                        "crs": crs_values,
                        "bbox": bbox,
                    }
                )

        return {
            "service": "WMS",
            "version": version,
            "title": service_title,
            "abstract": service_abstract,
            "layers": layers,
        }

    @staticmethod
    def _validate_bbox(bbox: tuple) -> tuple[float, float, float, float]:
        if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
            raise ValueError("bbox must contain four values (minx, miny, maxx, maxy)")
        minx, miny, maxx, maxy = (float(value) for value in bbox)
        if maxx <= minx or maxy <= miny:
            raise ValueError("bbox max values must be greater than min values")
        return minx, miny, maxx, maxy
