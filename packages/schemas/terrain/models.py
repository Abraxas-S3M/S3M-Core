"""Normalized terrain schemas for map layer and geospatial mission support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedMapLayer(BaseNormalizedRecord):
    layer_type: str = "elevation"
    format: str = "geojson"
    bounds: Dict[str, float] = field(default_factory=dict)
    resolution_m: Optional[float] = None
    tile_url_template: Optional[str] = None
    offline_path: Optional[str] = None


@dataclass
class ElevationTile:
    tile_id: str
    resolution_m: float


@dataclass
class TerrainProfile:
    profile_id: str
    elevations_m: List[float] = field(default_factory=list)
