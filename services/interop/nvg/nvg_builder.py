"""NVG XML builder for NATO tactical overlay interoperability."""

from __future__ import annotations

from math import cos, radians
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

from services.interop.symbology import SIDCGenerator, SymbologyMapper

if TYPE_CHECKING:
    from services.interop.models import ForceStructure


class NVGBuilder:
    """Build NATO Vector Graphics (NVG) XML overlays from S3M payloads."""

    def __init__(self, config: dict | None = None):
        cfg = dict(config or {})
        if isinstance(cfg.get("nvg"), dict):
            cfg = dict(cfg["nvg"])
        self.version = str(cfg.get("version", "2.0"))
        self.namespace = str(cfg.get("namespace", "http://tide.act.nato.int/schemas/2012/10/nvg"))
        self.clear()

    def clear(self) -> None:
        """Reset all in-memory tactical graphic elements before building XML."""
        self._points: List[Dict[str, Any]] = []
        self._polylines: List[Dict[str, Any]] = []
        self._polygons: List[Dict[str, Any]] = []
        self._circles: List[Dict[str, Any]] = []

    def add_point(
        self,
        lat: float,
        lon: float,
        symbol_sidc: str,
        label: str,
        speed: float | None = None,
        course: float | None = None,
    ) -> None:
        """Add a single tactical unit point with APP-6 / MIL-STD-2525 SIDC."""
        lat_value, lon_value = self._validate_lat_lon(lat, lon)
        sidc = self._resolve_sidc(
            provided_sidc=symbol_sidc,
            fallback_payload={"entity_type": str(label or "UNKNOWN"), "domain": "land"},
        )
        item: Dict[str, Any] = {
            "lat": lat_value,
            "lon": lon_value,
            "symbol": sidc,
            "label": str(label or "").strip(),
        }
        speed_value = self._safe_float(speed)
        course_value = self._safe_float(course)
        if speed_value is not None:
            item["speed"] = round(speed_value, 3)
        if course_value is not None:
            item["course"] = round(course_value, 3)
        self._points.append(item)

    def add_polyline(
        self,
        points: List[Tuple[float, float]],
        label: str,
        style: str | None = None,
    ) -> None:
        """Add a line overlay (phase line, route, boundary) to NVG output."""
        normalized = self._normalize_point_list(points, minimum_points=2)
        self._polylines.append(
            {
                "points": normalized,
                "label": str(label or "").strip(),
                "style": str(style).strip() if style else None,
            }
        )

    def add_polygon(
        self,
        points: List[Tuple[float, float]],
        label: str,
        style: str | None = None,
    ) -> None:
        """Add an area graphic (objective, AO, kill box) to NVG output."""
        normalized = self._normalize_point_list(points, minimum_points=3)
        self._polygons.append(
            {
                "points": normalized,
                "label": str(label or "").strip(),
                "style": str(style).strip() if style else None,
            }
        )

    def add_circle(
        self,
        lat: float,
        lon: float,
        radius_m: float,
        label: str,
        style: str | None = None,
    ) -> None:
        """Add a circular engagement/support zone to NVG output."""
        lat_value, lon_value = self._validate_lat_lon(lat, lon)
        radius = float(radius_m)
        if radius <= 0:
            raise ValueError("radius_m must be greater than zero")
        self._circles.append(
            {
                "lat": lat_value,
                "lon": lon_value,
                "radius_m": radius,
                "label": str(label or "").strip(),
                "style": str(style).strip() if style else None,
            }
        )

    def add_tracks(self, tracks: List[dict]) -> None:
        """Append S3M track records as NVG points."""
        if not isinstance(tracks, list):
            raise ValueError("tracks must be a list")
        for track in tracks:
            if not isinstance(track, dict):
                continue
            lat_lon = self._extract_lat_lon(track)
            if lat_lon is None:
                continue
            lat, lon = lat_lon
            sidc = self._resolve_sidc(
                provided_sidc=track.get("sidc"),
                fallback_payload={
                    "affiliation": track.get("affiliation", track.get("allegiance", "unknown")),
                    "domain": track.get("domain", "land"),
                    "entity_type": track.get("entity_type", track.get("role", track.get("type", "UNKNOWN"))),
                },
            )
            label = str(
                track.get("callsign")
                or track.get("name")
                or track.get("id")
                or track.get("unit_id")
                or track.get("uid")
                or "TRACK"
            )
            speed = track.get("speed", track.get("speed_mps"))
            course = track.get("heading", track.get("course", track.get("course_deg")))
            try:
                self.add_point(lat=lat, lon=lon, symbol_sidc=sidc, label=label, speed=speed, course=course)
            except ValueError:
                # Tactical robustness: skip malformed partner tracks but continue exporting valid COP points.
                continue

    def add_mission_layer(self, layer: dict) -> None:
        """Append mission planning graphics from GUIMissionLayer-like payload."""
        if not isinstance(layer, dict):
            raise ValueError("layer must be a dictionary")

        waypoints = layer.get("waypoints", [])
        waypoint_points = self._points_from_waypoint_sequence(waypoints)
        waypoint_lookup = self._build_waypoint_lookup(waypoints)
        mission_id = str(layer.get("missionId", layer.get("mission_id", "MISSION"))).strip() or "MISSION"

        if len(waypoint_points) >= 2:
            self.add_polyline(points=waypoint_points, label=f"Waypoints {mission_id}", style="stroke:#2b8cbe")

        for idx, phase in enumerate(layer.get("phaseLines", []) or [], start=1):
            if not isinstance(phase, dict):
                continue
            line_points = self._extract_phase_line_points(phase, waypoint_lookup)
            if len(line_points) < 2:
                continue
            label = str(phase.get("label") or phase.get("name") or phase.get("id") or f"Phase Line {idx}")
            self.add_polyline(points=line_points, label=label, style=phase.get("style"))

        for idx, objective in enumerate(layer.get("objectives", []) or [], start=1):
            if not isinstance(objective, dict):
                continue
            polygon_points = self._extract_objective_polygon(objective)
            if len(polygon_points) < 3:
                continue
            label = str(
                objective.get("label")
                or objective.get("name")
                or objective.get("id")
                or f"Objective {idx}"
            )
            self.add_polygon(points=polygon_points, label=label, style=objective.get("style"))

    def build(self) -> str:
        """Generate NVG XML document from currently staged tactical graphics."""
        root = ET.Element("nvg", {"xmlns": self.namespace, "version": self.version})

        for point in self._points:
            attrs = {
                "symbol": point["symbol"],
                "lat": self._float_str(point["lat"], precision=7),
                "lon": self._float_str(point["lon"], precision=7),
            }
            if point.get("label"):
                attrs["label"] = point["label"]
            node = ET.SubElement(root, "point", attrs)
            if point.get("speed") is not None or point.get("course") is not None:
                ext = ET.SubElement(node, "ExtendedData")
                if point.get("speed") is not None:
                    speed_node = ET.SubElement(ext, "SimpleData", {"name": "speed"})
                    speed_node.text = self._float_str(point["speed"], precision=3)
                if point.get("course") is not None:
                    course_node = ET.SubElement(ext, "SimpleData", {"name": "course"})
                    course_node.text = self._float_str(point["course"], precision=3)

        for line in self._polylines:
            attrs = {
                "points": self._format_points_attr(line["points"]),
                "label": str(line.get("label", "")),
            }
            if line.get("style"):
                attrs["style"] = str(line["style"])
            ET.SubElement(root, "polyline", attrs)

        for polygon in self._polygons:
            attrs = {
                "points": self._format_points_attr(polygon["points"]),
                "label": str(polygon.get("label", "")),
            }
            if polygon.get("style"):
                attrs["style"] = str(polygon["style"])
            ET.SubElement(root, "polygon", attrs)

        for circle in self._circles:
            attrs = {
                "cx": self._float_str(circle["lat"], precision=7),
                "cy": self._float_str(circle["lon"], precision=7),
                "r": self._float_str(circle["radius_m"], precision=3),
                "label": str(circle.get("label", "")),
            }
            if circle.get("style"):
                attrs["style"] = str(circle["style"])
            ET.SubElement(root, "circle", attrs)

        return ET.tostring(root, encoding="unicode")

    def from_tracks(self, tracks: List[dict]) -> str:
        """Convert S3M tracks to NVG point graphics and return XML."""
        self.clear()
        self.add_tracks(tracks)
        return self.build()

    def from_mission_layer(self, layer: dict) -> str:
        """Convert GUIMissionLayer-style overlays into NVG document XML."""
        self.clear()
        self.add_mission_layer(layer)
        return self.build()

    def from_orbat(self, force: "ForceStructure") -> str:
        """Convert ORBAT force structure units into NVG point symbols."""
        self.clear()
        units = getattr(force, "units", None)
        if not isinstance(units, list):
            raise ValueError("force must provide a units list")
        force_affiliation = getattr(force, "affiliation", "unknown")
        for unit in units:
            if not unit.position or len(unit.position) < 2:
                continue
            lat, lon = float(unit.position[0]), float(unit.position[1])
            unit_domain = self._unit_domain(unit.unit_type)
            sidc = self._resolve_sidc(
                provided_sidc=unit.nato_symbol,
                fallback_payload={
                    "affiliation": unit.affiliation or force_affiliation,
                    "domain": unit_domain,
                    "entity_type": unit.unit_type or unit.name,
                },
            )
            label = str(unit.designation or unit.name or unit.unit_id)
            self.add_point(lat=lat, lon=lon, symbol_sidc=sidc, label=label)
        return self.build()

    @staticmethod
    def _float_str(value: float, precision: int) -> str:
        return f"{float(value):.{int(precision)}f}".rstrip("0").rstrip(".")

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_lat_lon(lat: float, lon: float) -> Tuple[float, float]:
        lat_value = float(lat)
        lon_value = float(lon)
        if not (-90.0 <= lat_value <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        if not (-180.0 <= lon_value <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return lat_value, lon_value

    def _normalize_point_list(
        self,
        points: Iterable[Tuple[float, float]],
        minimum_points: int,
    ) -> List[Tuple[float, float]]:
        normalized: List[Tuple[float, float]] = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            lat, lon = self._validate_lat_lon(point[0], point[1])
            normalized.append((lat, lon))
        if len(normalized) < minimum_points:
            raise ValueError(f"points must contain at least {minimum_points} valid coordinates")
        return normalized

    def _resolve_sidc(self, provided_sidc: Any, fallback_payload: Dict[str, Any]) -> str:
        sidc = str(provided_sidc or "").strip()
        if SIDCGenerator.is_valid_sidc(sidc):
            return sidc
        mapped = SymbologyMapper.map_track_symbology(fallback_payload)
        if SIDCGenerator.is_valid_sidc(mapped):
            return mapped
        return SIDCGenerator.generate(
            affiliation=str(fallback_payload.get("affiliation", "unknown")),
            domain=str(fallback_payload.get("domain", "land")),
            entity_type=str(fallback_payload.get("entity_type", "UNKNOWN")),
        )

    def _extract_lat_lon(self, payload: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        position = payload.get("position")
        if isinstance(position, (list, tuple)) and len(position) >= 2:
            try:
                return self._validate_lat_lon(position[0], position[1])
            except Exception:
                return None
        if isinstance(position, dict):
            lat = position.get("lat", position.get("latitude"))
            lon = position.get("lon", position.get("longitude"))
            if lat is not None and lon is not None:
                try:
                    return self._validate_lat_lon(lat, lon)
                except Exception:
                    return None
        lat = payload.get("lat", payload.get("latitude"))
        lon = payload.get("lon", payload.get("longitude"))
        if lat is None or lon is None:
            x = payload.get("x")
            y = payload.get("y")
            if x is not None and y is not None:
                return self._grid_to_geo(float(x), float(y))
        if lat is None or lon is None:
            return None
        try:
            return self._validate_lat_lon(lat, lon)
        except Exception:
            return None

    @staticmethod
    def _grid_to_geo(x_meters: float, y_meters: float) -> Tuple[float, float]:
        # Tactical context: planner mission graphics can be mission-grid based; convert
        # to geodetic coordinates so coalition NVG overlays render on map baselayers.
        base_lat = 24.7136
        base_lon = 46.6753
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = meters_per_deg_lat * max(0.1, cos(radians(base_lat)))
        latitude = base_lat + (y_meters / meters_per_deg_lat)
        longitude = base_lon + (x_meters / meters_per_deg_lon)
        return round(latitude, 6), round(longitude, 6)

    def _points_from_waypoint_sequence(self, waypoints: Any) -> List[Tuple[float, float]]:
        if not isinstance(waypoints, list):
            return []
        points: List[Tuple[float, float]] = []
        for waypoint in waypoints:
            if not isinstance(waypoint, dict):
                continue
            lat_lon = self._extract_lat_lon(waypoint)
            if lat_lon is not None:
                points.append(lat_lon)
        return points

    def _build_waypoint_lookup(self, waypoints: Any) -> Dict[str, Tuple[float, float]]:
        lookup: Dict[str, Tuple[float, float]] = {}
        if not isinstance(waypoints, list):
            return lookup
        for waypoint in waypoints:
            if not isinstance(waypoint, dict):
                continue
            waypoint_id = str(waypoint.get("id", "")).strip()
            lat_lon = self._extract_lat_lon(waypoint)
            if waypoint_id and lat_lon is not None:
                lookup[waypoint_id] = lat_lon
        return lookup

    def _extract_phase_line_points(
        self,
        phase_line: Dict[str, Any],
        waypoint_lookup: Dict[str, Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        raw_points = phase_line.get("points", phase_line.get("coordinates"))
        points = self._extract_coordinate_list(raw_points)
        if len(points) >= 2:
            return points
        from_id = str(phase_line.get("from", "")).strip()
        to_id = str(phase_line.get("to", "")).strip()
        if from_id in waypoint_lookup and to_id in waypoint_lookup:
            return [waypoint_lookup[from_id], waypoint_lookup[to_id]]
        return []

    def _extract_objective_polygon(self, objective: Dict[str, Any]) -> List[Tuple[float, float]]:
        for key in ("points", "polygon", "coordinates"):
            points = self._extract_coordinate_list(objective.get(key))
            if len(points) >= 3:
                return points
        return []

    def _extract_coordinate_list(self, raw_points: Any) -> List[Tuple[float, float]]:
        if not isinstance(raw_points, list):
            return []
        points: List[Tuple[float, float]] = []
        for entry in raw_points:
            if isinstance(entry, dict):
                x_value = self._safe_float(entry.get("x"))
                y_value = self._safe_float(entry.get("y"))
                if x_value is not None and y_value is not None:
                    points.append(self._grid_to_geo(x_value, y_value))
                    continue
                lat_lon = self._extract_lat_lon(entry)
                if lat_lon is not None:
                    points.append(lat_lon)
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    points.append(self._validate_lat_lon(entry[0], entry[1]))
                except Exception:
                    continue
        return points

    def _format_points_attr(self, points: List[Tuple[float, float]]) -> str:
        return " ".join(
            f"{self._float_str(lat, precision=7)},{self._float_str(lon, precision=7)}" for lat, lon in points
        )

    @staticmethod
    def _unit_domain(unit_type: Any) -> str:
        text = str(unit_type or "").strip().lower()
        if any(token in text for token in ("air", "aviation", "uav", "airborne", "helicopter")):
            return "air"
        if any(token in text for token in ("naval", "ship", "maritime", "surface")):
            return "surface"
        return "land"
