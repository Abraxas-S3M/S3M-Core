"""NVG XML parser for NATO tactical overlay interoperability."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET


class NVGParser:
    """Parse NVG overlays and convert them into S3M ingestion payloads."""

    _MAX_XML_BYTES = 512_000

    def __init__(self, config: dict | None = None):
        cfg = dict(config or {})
        if isinstance(cfg.get("nvg"), dict):
            cfg = dict(cfg["nvg"])
        self.namespace = str(cfg.get("namespace", "http://tide.act.nato.int/schemas/2012/10/nvg"))
        self.supported_namespaces = {
            self.namespace,
            "http://tide.act.nato.int/schemas/2010/09/nvg",  # legacy NVG 1.5 deployments
            "http://tide.act.nato.int/schemas/2009/10/nvg",  # legacy NVG 1.4 deployments
        }

    def parse(self, xml_str: str) -> dict:
        """Parse NVG XML into normalized geometric and point feature lists."""
        root = self._safe_parse_xml(xml_str)
        root_namespace = self._extract_namespace(root.tag)
        if root_namespace and root_namespace not in self.supported_namespaces:
            raise ValueError(f"unsupported NVG namespace: {root_namespace}")

        parsed = {
            "namespace": root_namespace,
            "version": str(root.attrib.get("version", "unknown")),
            "points": [],
            "polylines": [],
            "polygons": [],
            "circles": [],
        }
        for node in list(root):
            tag = self._local_name(node.tag)
            if tag == "point":
                parsed["points"].append(self._parse_point(node))
            elif tag == "polyline":
                parsed["polylines"].append(self._parse_line_or_polygon(node, geometry="polyline"))
            elif tag == "polygon":
                parsed["polygons"].append(self._parse_line_or_polygon(node, geometry="polygon"))
            elif tag == "circle":
                parsed["circles"].append(self._parse_circle(node))
        return parsed

    def to_tracks(self, parsed: dict) -> List[dict]:
        """Convert parsed NVG points into ForceAwareness-compatible S3M tracks."""
        if not isinstance(parsed, dict):
            raise ValueError("parsed must be a dictionary")
        tracks: List[dict] = []
        for idx, point in enumerate(parsed.get("points", []), start=1):
            if not isinstance(point, dict):
                continue
            lat = point.get("lat")
            lon = point.get("lon")
            if lat is None or lon is None:
                continue
            label = str(point.get("label", "")).strip()
            track_id = self._normalize_track_id(label or f"NVG-TRACK-{idx}")
            row: Dict[str, Any] = {
                "unit_id": track_id,
                "id": track_id,
                "position": [float(lat), float(lon), 0.0],
                "role": "nvg_point",
                "status": "active",
                "source": "nvg",
                "callsign": label or track_id,
                "sidc": str(point.get("symbol", "")).strip(),
            }
            if point.get("speed") is not None:
                row["speed"] = float(point["speed"])
            if point.get("course") is not None:
                row["heading"] = float(point["course"])
            tracks.append(row)
        return tracks

    def to_mission_layer(self, parsed: dict) -> dict:
        """Convert NVG graphics into GUIMissionLayer-style planning overlays."""
        if not isinstance(parsed, dict):
            raise ValueError("parsed must be a dictionary")

        phase_lines: List[Dict[str, Any]] = []
        waypoints: List[Dict[str, Any]] = []
        objectives: List[Dict[str, Any]] = []

        waypoint_seen: set[Tuple[float, float]] = set()
        waypoint_idx = 1

        for idx, line in enumerate(parsed.get("polylines", []), start=1):
            if not isinstance(line, dict):
                continue
            points = self._coerce_points(line.get("points"))
            if len(points) < 2:
                continue
            label = str(line.get("label") or f"Phase Line {idx}")
            phase_lines.append(
                {
                    "id": str(line.get("id") or f"PHASE-LINE-{idx}"),
                    "label": label,
                    "style": line.get("style"),
                    "points": [{"lat": p[0], "lon": p[1]} for p in points],
                }
            )
            # Tactical context: preserve each unique control point as a GUI waypoint.
            for point in points:
                if point in waypoint_seen:
                    continue
                waypoint_seen.add(point)
                waypoints.append({"id": f"WP-{waypoint_idx}", "lat": point[0], "lon": point[1], "z": 0.0})
                waypoint_idx += 1

        for idx, polygon in enumerate(parsed.get("polygons", []), start=1):
            if not isinstance(polygon, dict):
                continue
            points = self._coerce_points(polygon.get("points"))
            if len(points) < 3:
                continue
            objectives.append(
                {
                    "id": str(polygon.get("id") or f"OBJ-{idx}"),
                    "label": str(polygon.get("label") or f"Objective {idx}"),
                    "style": polygon.get("style"),
                    "status": "planned",
                    "points": [{"lat": p[0], "lon": p[1]} for p in points],
                }
            )

        return {
            "missionId": "nvg-import",
            "waypoints": waypoints,
            "phaseLines": phase_lines,
            "objectives": objectives,
        }

    def _parse_point(self, node: ET.Element) -> dict:
        lat = self._safe_float(node.attrib.get("lat"))
        lon = self._safe_float(node.attrib.get("lon"))
        payload: Dict[str, Any] = {
            "symbol": str(node.attrib.get("symbol", "")),
            "lat": lat,
            "lon": lon,
            "label": str(node.attrib.get("label", "")),
        }
        speed = None
        course = None
        for child in list(node):
            if self._local_name(child.tag) != "ExtendedData":
                continue
            for entry in list(child):
                if self._local_name(entry.tag) != "SimpleData":
                    continue
                key = str(entry.attrib.get("name", "")).strip().lower()
                value = self._safe_float(entry.text)
                if key == "speed" and value is not None:
                    speed = value
                if key in {"course", "heading"} and value is not None:
                    course = value
        if speed is not None:
            payload["speed"] = speed
        if course is not None:
            payload["course"] = course
        return payload

    def _parse_line_or_polygon(self, node: ET.Element, geometry: str) -> dict:
        points = self._parse_points_attr(node.attrib.get("points", ""))
        return {
            "geometry": geometry,
            "label": str(node.attrib.get("label", "")),
            "style": str(node.attrib.get("style", "")),
            "points": points,
        }

    def _parse_circle(self, node: ET.Element) -> dict:
        return {
            "lat": self._safe_float(node.attrib.get("cx")),
            "lon": self._safe_float(node.attrib.get("cy")),
            "radius_m": self._safe_float(node.attrib.get("r")),
            "label": str(node.attrib.get("label", "")),
            "style": str(node.attrib.get("style", "")),
        }

    def _parse_points_attr(self, points_attr: str) -> List[Tuple[float, float]]:
        points: List[Tuple[float, float]] = []
        raw = str(points_attr or "").strip()
        if not raw:
            return points
        for token in raw.split():
            if "," not in token:
                continue
            lat_raw, lon_raw = token.split(",", 1)
            lat = self._safe_float(lat_raw)
            lon = self._safe_float(lon_raw)
            if lat is None or lon is None:
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                continue
            points.append((lat, lon))
        return points

    def _safe_parse_xml(self, xml_str: str) -> ET.Element:
        if not isinstance(xml_str, str):
            raise ValueError("xml_str must be a string")
        raw = xml_str.strip()
        if not raw:
            raise ValueError("xml_str is empty")
        if len(raw.encode("utf-8")) > self._MAX_XML_BYTES:
            raise ValueError("xml_str exceeds size limit")
        lowered = raw.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            raise ValueError("unsafe XML declaration is not allowed")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ValueError("invalid NVG XML") from exc

        if self._local_name(root.tag) != "nvg":
            raise ValueError("NVG XML root must be <nvg>")
        return root

    @staticmethod
    def _extract_namespace(tag: str) -> str:
        text = str(tag or "")
        if text.startswith("{") and "}" in text:
            return text[1 : text.index("}")]
        return ""

    @staticmethod
    def _local_name(tag: str) -> str:
        text = str(tag or "")
        if text.startswith("{") and "}" in text:
            return text[text.index("}") + 1 :]
        return text

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_track_id(label: str) -> str:
        text = str(label or "").strip().replace(" ", "-")
        return text if text else "NVG-TRACK"

    def _coerce_points(self, points: Any) -> List[Tuple[float, float]]:
        if not isinstance(points, list):
            return []
        result: List[Tuple[float, float]] = []
        for entry in points:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            lat = self._safe_float(entry[0])
            lon = self._safe_float(entry[1])
            if lat is None or lon is None:
                continue
            result.append((lat, lon))
        return result
