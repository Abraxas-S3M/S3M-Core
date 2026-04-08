"""Lightweight ORBAT store for tactical force structure visualization."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Unit:
    id: str
    name: str
    sidc: str
    parent_id: str | None = None
    subordinates: list[str] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)
    position: dict[str, float] | None = None


class ORBATStore:
    """Stores imported ORBAT units and exposes hierarchy query helpers."""

    def __init__(self) -> None:
        self._units: dict[str, Unit] = {}

    def load_from_json(self, path: str) -> None:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string")
        src = Path(path)
        payload = json.loads(src.read_text(encoding="utf-8"))
        raw_units = self._extract_raw_units(payload)
        units: dict[str, Unit] = {}
        for idx, raw in enumerate(raw_units, start=1):
            parsed = self._parse_raw_unit(raw, idx=idx)
            units[parsed.id] = parsed
        self._units = units
        self._link_parent_child_relationships()

    def get_hierarchy(self) -> list[dict[str, Any]]:
        children: dict[str, list[Unit]] = {}
        roots: list[Unit] = []
        for unit in self._units.values():
            if unit.parent_id and unit.parent_id in self._units:
                children.setdefault(unit.parent_id, []).append(unit)
            else:
                roots.append(unit)

        def _build_tree(node: Unit) -> dict[str, Any]:
            subordinates = sorted(children.get(node.id, []), key=lambda child: child.id)
            return {
                "id": node.id,
                "name": node.name,
                "sidc": node.sidc,
                "parent_id": node.parent_id,
                "equipment": list(node.equipment),
                "position": dict(node.position) if node.position else None,
                "subordinates": [_build_tree(child) for child in subordinates],
            }

        return [_build_tree(root) for root in sorted(roots, key=lambda item: item.id)]

    def get_unit(self, unit_id: str) -> Unit | None:
        if not isinstance(unit_id, str) or not unit_id.strip():
            return None
        return self._units.get(unit_id)

    def get_equipment_summary(self) -> dict[str, int]:
        counts = Counter()
        for unit in self._units.values():
            counts.update(unit.equipment)
        return dict(counts)

    def _extract_raw_units(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []

        for key in ("units", "orbat", "items", "elements"):
            maybe = payload.get(key)
            if isinstance(maybe, list):
                return maybe

        features = payload.get("features")
        if isinstance(features, list):
            return features

        if "id" in payload or "unit_id" in payload:
            return [payload]
        return []

    def _parse_raw_unit(self, raw: Any, *, idx: int) -> Unit:
        source = raw if isinstance(raw, dict) else {}
        if source.get("type") == "Feature":
            props = source.get("properties", {}) if isinstance(source.get("properties"), dict) else {}
            geometry = source.get("geometry", {}) if isinstance(source.get("geometry"), dict) else {}
            source = {**props, **{"_feature_id": source.get("id"), "_geometry": geometry}}

        unit_id = self._first_non_empty(
            source.get("id"),
            source.get("unit_id"),
            source.get("unitId"),
            source.get("_feature_id"),
            f"unit-{idx}",
        )
        parent_id = self._first_non_empty(
            source.get("parent_id"),
            source.get("parentId"),
            source.get("parent"),
            source.get("parentUnitId"),
            default=None,
        )
        equipment = self._normalize_equipment(source.get("equipment", []))
        subordinates = self._normalize_subordinates(source.get("subordinates", []))
        position = self._normalize_position(
            source.get("position"),
            source.get("_geometry"),
        )
        return Unit(
            id=unit_id,
            name=self._first_non_empty(source.get("name"), source.get("title"), unit_id),
            sidc=self._first_non_empty(source.get("sidc"), source.get("symbolCode"), ""),
            parent_id=parent_id,
            subordinates=subordinates,
            equipment=equipment,
            position=position,
        )

    def _link_parent_child_relationships(self) -> None:
        for unit in self._units.values():
            if unit.parent_id and unit.parent_id in self._units:
                parent = self._units[unit.parent_id]
                if unit.id not in parent.subordinates:
                    parent.subordinates.append(unit.id)

        for unit in self._units.values():
            for child_id in list(unit.subordinates):
                child = self._units.get(child_id)
                if child and not child.parent_id:
                    child.parent_id = unit.id

    def _normalize_equipment(self, equipment: Any) -> list[str]:
        if not isinstance(equipment, list):
            return []
        normalized: list[str] = []
        for item in equipment:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
            elif isinstance(item, dict):
                name = self._first_non_empty(item.get("name"), item.get("type"), default="")
                if name:
                    normalized.append(name)
        return normalized

    def _normalize_subordinates(self, subordinates: Any) -> list[str]:
        if not isinstance(subordinates, list):
            return []
        normalized: list[str] = []
        for item in subordinates:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
            elif isinstance(item, dict):
                unit_id = self._first_non_empty(
                    item.get("id"),
                    item.get("unit_id"),
                    item.get("unitId"),
                    default="",
                )
                if unit_id:
                    normalized.append(unit_id)
        return normalized

    def _normalize_position(self, position: Any, geometry: Any) -> dict[str, float] | None:
        if isinstance(position, dict):
            lat = position.get("lat")
            lon = position.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return {"lat": float(lat), "lon": float(lon)}
        if isinstance(geometry, dict):
            coords = geometry.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                lon, lat = coords[0], coords[1]
                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                    return {"lat": float(lat), "lon": float(lon)}
        return None

    def _first_non_empty(self, *values: Any, default: str | None = "") -> str | None:
        for value in values:
            if value is None:
                continue
            as_str = str(value).strip()
            if as_str:
                return as_str
        return default
