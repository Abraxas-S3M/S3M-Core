"""GeoJSON bridge adapter for OGC, NVG, and S3M internal models."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from xml.etree import ElementTree as ET


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoJSONAdapter:
    """Convert S3M track and mission structures to/from GeoJSON."""

    def tracks_to_geojson(self, tracks: list[dict]) -> dict:
        """Convert S3M track rows to GeoJSON FeatureCollection."""
        if not isinstance(tracks, list):
            raise ValueError("tracks must be a list of dictionaries")

        features: list[dict[str, Any]] = []
        for track in tracks:
            if not isinstance(track, dict):
                continue

            lon, lat, alt = self._extract_position(track)
            properties = {
                "track_id": str(track.get("track_id") or track.get("unit_id") or "").strip(),
                "callsign": str(track.get("callsign") or track.get("name") or "").strip(),
                "affiliation": str(track.get("affiliation") or "unknown").strip(),
                "status": str(track.get("status") or "active").strip(),
                "speed": self._as_float(track.get("speed"), 0.0),
                "heading": self._as_float(track.get("heading"), 0.0),
                "timestamp": str(track.get("timestamp") or track.get("time") or _iso_utc_now()),
            }
            properties = {key: value for key, value in properties.items() if value not in {"", None}}

            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat, alt],
                    },
                    "properties": properties,
                }
            )

        return {"type": "FeatureCollection", "features": features}

    def mission_to_geojson(self, mission_layer: dict) -> dict:
        """Convert mission waypoints/objectives into GeoJSON features."""
        if not isinstance(mission_layer, dict):
            raise ValueError("mission_layer must be a dictionary")

        features: list[dict[str, Any]] = []

        for waypoint in mission_layer.get("waypoints", []):
            if not isinstance(waypoint, dict):
                continue
            lon, lat, alt = self._extract_position(waypoint)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat, alt]},
                    "properties": {
                        "kind": "waypoint",
                        "id": str(waypoint.get("id") or waypoint.get("waypoint_id") or "").strip(),
                        "label": str(waypoint.get("label") or waypoint.get("name") or "").strip(),
                    },
                }
            )

        objectives = mission_layer.get("objectives", [])
        for objective in objectives:
            if not isinstance(objective, dict):
                continue
            lon, lat, alt = self._extract_position(objective)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat, alt]},
                    "properties": {
                        "kind": "objective",
                        "id": str(objective.get("id") or objective.get("objective_id") or "").strip(),
                        "label": str(objective.get("label") or objective.get("name") or "").strip(),
                        "priority": str(objective.get("priority") or "").strip(),
                    },
                }
            )

        path_points = mission_layer.get("path", [])
        if isinstance(path_points, list) and len(path_points) >= 2:
            coordinates: list[list[float]] = []
            for point in path_points:
                if isinstance(point, dict):
                    lon, lat, alt = self._extract_position(point)
                    coordinates.append([lon, lat, alt])
                elif isinstance(point, (list, tuple)) and len(point) >= 2:
                    lon = self._as_float(point[0], 0.0)
                    lat = self._as_float(point[1], 0.0)
                    alt = self._as_float(point[2], 0.0) if len(point) > 2 else 0.0
                    coordinates.append([lon, lat, alt])
            if len(coordinates) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coordinates},
                        "properties": {"kind": "route", "id": str(mission_layer.get("mission_id") or "").strip()},
                    }
                )

        return {"type": "FeatureCollection", "features": features}

    def geojson_to_tracks(self, geojson: dict) -> list[dict]:
        """Parse GeoJSON features into normalized S3M track dictionaries."""
        self._validate_geojson_feature_collection(geojson)
        tracks: list[dict[str, Any]] = []

        for feature in geojson.get("features", []):
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry", {})
            properties = feature.get("properties", {})
            if not isinstance(geometry, dict) or geometry.get("type") != "Point":
                continue
            coordinates = geometry.get("coordinates", [])
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                continue
            lon = self._as_float(coordinates[0], 0.0)
            lat = self._as_float(coordinates[1], 0.0)
            alt = self._as_float(coordinates[2], 0.0) if len(coordinates) > 2 else 0.0

            if not isinstance(properties, dict):
                properties = {}
            track_id = str(properties.get("track_id") or properties.get("unit_id") or "").strip()
            callsign = str(properties.get("callsign") or properties.get("name") or "").strip()
            timestamp = str(properties.get("timestamp") or properties.get("time") or _iso_utc_now())

            tracks.append(
                {
                    "track_id": track_id or f"track-{len(tracks) + 1}",
                    "callsign": callsign or track_id or "unknown",
                    "position": [lon, lat, alt],
                    "affiliation": str(properties.get("affiliation") or "unknown").strip(),
                    "status": str(properties.get("status") or "active").strip(),
                    "heading": self._as_float(properties.get("heading"), 0.0),
                    "speed": self._as_float(properties.get("speed"), 0.0),
                    "timestamp": timestamp,
                }
            )

        return tracks

    def nvg_to_geojson(self, nvg_parsed: dict) -> dict:
        """Convert parsed NVG element dictionary into GeoJSON."""
        if not isinstance(nvg_parsed, dict):
            raise ValueError("nvg_parsed must be a dictionary")

        items = nvg_parsed.get("elements", [])
        if not isinstance(items, list):
            items = []

        features: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "point").strip().lower()
            props = dict(item.get("properties") or {})
            if not isinstance(props, dict):
                props = {}
            props.setdefault("nvg_type", kind)

            if kind == "line":
                points = item.get("points", [])
                coords = self._normalize_points(points)
                if len(coords) >= 2:
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": coords},
                            "properties": props,
                        }
                    )
            elif kind == "polygon":
                points = item.get("points", [])
                coords = self._normalize_points(points)
                if len(coords) >= 3:
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [coords]},
                            "properties": props,
                        }
                    )
            else:
                lon, lat, alt = self._extract_position(item)
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat, alt]},
                        "properties": props,
                    }
                )

        return {"type": "FeatureCollection", "features": features}

    def geojson_to_nvg(self, geojson: dict) -> str:
        """Convert GeoJSON FeatureCollection to lightweight NVG XML."""
        self._validate_geojson_feature_collection(geojson)

        root = ET.Element("nvg")
        root.set("version", "1.0")
        root.set("generated", _iso_utc_now())

        for feature in geojson.get("features", []):
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry", {})
            properties = feature.get("properties", {})
            if not isinstance(geometry, dict):
                continue
            if not isinstance(properties, dict):
                properties = {}

            geom_type = str(geometry.get("type") or "").strip()
            coordinates = geometry.get("coordinates")
            if geom_type == "Point":
                if not isinstance(coordinates, list) or len(coordinates) < 2:
                    continue
                elem = ET.SubElement(root, "point")
                elem.set("lon", str(self._as_float(coordinates[0], 0.0)))
                elem.set("lat", str(self._as_float(coordinates[1], 0.0)))
                elem.set("alt", str(self._as_float(coordinates[2], 0.0) if len(coordinates) > 2 else 0.0))
                self._append_properties(elem, properties)
            elif geom_type == "LineString":
                if not isinstance(coordinates, list) or len(coordinates) < 2:
                    continue
                elem = ET.SubElement(root, "line")
                self._append_line_points(elem, coordinates)
                self._append_properties(elem, properties)
            elif geom_type == "Polygon":
                if not isinstance(coordinates, list) or not coordinates:
                    continue
                ring = coordinates[0]
                if not isinstance(ring, list) or len(ring) < 3:
                    continue
                elem = ET.SubElement(root, "polygon")
                self._append_line_points(elem, ring)
                self._append_properties(elem, properties)

        return ET.tostring(root, encoding="unicode")

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _extract_position(self, item: dict[str, Any]) -> tuple[float, float, float]:
        position = item.get("position")
        if isinstance(position, (list, tuple)) and len(position) >= 2:
            lon = self._as_float(position[0], self._as_float(item.get("lon"), 0.0))
            lat = self._as_float(position[1], self._as_float(item.get("lat"), 0.0))
            alt = self._as_float(position[2], self._as_float(item.get("alt"), 0.0)) if len(position) > 2 else self._as_float(item.get("alt"), 0.0)
            return lon, lat, alt
        return (
            self._as_float(item.get("lon"), 0.0),
            self._as_float(item.get("lat"), 0.0),
            self._as_float(item.get("alt"), self._as_float(item.get("hae"), 0.0)),
        )

    def _normalize_points(self, points: Any) -> list[list[float]]:
        normalized: list[list[float]] = []
        if not isinstance(points, list):
            return normalized
        for point in points:
            if isinstance(point, dict):
                lon, lat, alt = self._extract_position(point)
                normalized.append([lon, lat, alt])
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                lon = self._as_float(point[0], 0.0)
                lat = self._as_float(point[1], 0.0)
                alt = self._as_float(point[2], 0.0) if len(point) > 2 else 0.0
                normalized.append([lon, lat, alt])
        return normalized

    @staticmethod
    def _validate_geojson_feature_collection(geojson: dict) -> None:
        if not isinstance(geojson, dict):
            raise ValueError("geojson must be a dictionary")
        if geojson.get("type") != "FeatureCollection":
            raise ValueError("geojson.type must be 'FeatureCollection'")
        if not isinstance(geojson.get("features"), list):
            raise ValueError("geojson.features must be a list")

    @staticmethod
    def _append_properties(elem: ET.Element, properties: dict[str, Any]) -> None:
        props = ET.SubElement(elem, "properties")
        for key, value in properties.items():
            if value is None:
                continue
            prop = ET.SubElement(props, "property")
            prop.set("name", str(key))
            prop.text = str(value)

    def _append_line_points(self, elem: ET.Element, coordinates: list[Any]) -> None:
        for coordinate in coordinates:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            node = ET.SubElement(elem, "pt")
            node.set("lon", str(self._as_float(coordinate[0], 0.0)))
            node.set("lat", str(self._as_float(coordinate[1], 0.0)))
            node.set("alt", str(self._as_float(coordinate[2], 0.0) if len(coordinate) > 2 else 0.0))

