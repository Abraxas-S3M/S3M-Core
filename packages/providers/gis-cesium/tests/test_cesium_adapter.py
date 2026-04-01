from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.gis_cesium.adapter import CesiumAdapter
from packages.providers.gis_cesium.config import CesiumConfig
from packages.providers.gis_cesium.normalizer import CesiumNormalizer


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = CesiumAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "gis-cesium"
    assert manifest.tier == "FREEMIUM"
    assert manifest.auth_type == "api_key"


def test_world_terrain_asset_id() -> None:
    assert CesiumConfig().world_terrain_asset_id == 1


def test_normalize_terrain_layer_type() -> None:
    fixture = json.loads((FIXTURE_DIR / "terrain_metadata.json").read_text(encoding="utf-8"))
    layer = CesiumNormalizer().normalize_terrain_metadata(fixture)
    assert layer.layer_type == "elevation"


def test_normalize_3d_tileset() -> None:
    tileset = json.loads((FIXTURE_DIR / "tileset_root.json").read_text(encoding="utf-8"))
    layer = CesiumNormalizer().normalize_3d_tileset(tileset)
    assert layer.format == "3dtiles"


def test_terrain_resolution_from_zoom() -> None:
    n = CesiumNormalizer()
    assert n.resolution_from_zoom(12) == 30.0
    assert n.resolution_from_zoom(14) == 10.0


def test_bounding_volume_parsing() -> None:
    n = CesiumNormalizer()
    box = n._bounds_from_bounding_volume({"box": [0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3]})
    sphere = n._bounds_from_bounding_volume({"sphere": [1, 2, 3, 4]})
    assert "half_x" in box and "half_y" in box and "half_z" in box
    assert sphere["radius_m"] == 4


def test_generate_offline_region() -> None:
    out = CesiumAdapter(mode="airgapped").generate_offline_terrain("riyadh_metro", max_zoom=12)
    assert "tile_count" in out
    assert "size_mb" in out


def test_fetch_airgapped_reads_cache(tmp_path: Path) -> None:
    adapter = CesiumAdapter(mode="airgapped")
    adapter.terrain_cache = tmp_path
    tile = tmp_path / "12_2460_1600.terrain"
    tile.write_bytes(b"terrain")
    assert adapter.fetch_terrain_tile(12, 2460, 1600) == b"terrain"
