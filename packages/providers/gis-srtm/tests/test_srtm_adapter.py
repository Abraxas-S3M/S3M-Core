from __future__ import annotations

import os
import sys
from array import array
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.gis_srtm.adapter import SRTMAdapter
from packages.providers.gis_srtm.config import SRTMConfig
from packages.providers.gis_srtm.normalizer import SRTMNormalizer


def test_manifest_correct() -> None:
    manifest = SRTMAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "gis-srtm"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "api_key"
    assert "OPENTOPOGRAPHY_API_KEY" in manifest.optional_env_vars


def test_tile_name_from_latlon() -> None:
    n = SRTMNormalizer()
    assert n.tile_name_from_latlon(24.71, 46.68) == "N24E046.hgt"
    assert n.tile_name_from_latlon(-33.5, -70.6) == "S34W071.hgt"


def test_hgt_tile_dimensions() -> None:
    assert SRTMConfig().tile_size == 3601


def test_bilinear_interpolation() -> None:
    grid = [[100, 110], [120, 130]]
    value = SRTMNormalizer().bilinear_interpolate(grid, 0.5, 0.5)
    assert value == 115.0


def test_elevation_riyadh() -> None:
    elev = SRTMAdapter(mode="airgapped").get_elevation(24.7136, 46.6753)
    assert elev is not None
    assert 560 <= elev <= 660


def test_elevation_profile_ascent() -> None:
    profile = SRTMAdapter(mode="airgapped").get_elevation_profile([(24.7136, 46.6753), (21.4858, 39.1925)], num_samples=50)
    assert len(profile) == 50
    assert max(item["elevation_m"] for item in profile) >= 2100


def test_slope_computation() -> None:
    adapter = SRTMAdapter(mode="airgapped")

    def flat(_lat: float, _lon: float) -> float:
        return 100.0

    adapter.get_elevation = flat  # type: ignore[assignment]
    slope_flat = adapter.compute_slope(24.7, 46.6)
    assert slope_flat["slope_deg"] <= 0.1

    def steep(lat: float, lon: float) -> float:
        return 1000.0 + (lat * 10000.0)

    adapter.get_elevation = steep  # type: ignore[assignment]
    slope_steep = adapter.compute_slope(24.7, 46.6)
    assert slope_steep["slope_deg"] > 30.0


def test_viewshed_radius() -> None:
    adapter = SRTMAdapter(mode="airgapped")
    out = adapter.compute_viewshed(24.7, 46.6, radius_km=1.0)
    points = out["visible_points"] + out["hidden_points"]
    assert len(points) > 0
    for lat, lon in points:
        d = adapter._distance_m((24.7, 46.6), (lat, lon))
        assert d <= 1500.0


def test_line_of_sight_obstruction() -> None:
    adapter = SRTMAdapter(mode="airgapped")

    def with_ridge(lat: float, lon: float) -> float:
        if 0.45 < lon < 0.55:
            return 200.0
        return 10.0

    adapter.get_elevation = with_ridge  # type: ignore[assignment]
    los = adapter.check_line_of_sight((0.0, 0.0), (0.0, 1.0), height_a_m=2.0, height_b_m=2.0)
    assert los["visible"] is False
    assert los["max_obstruction_m"] > 0.0


def test_line_of_sight_clear() -> None:
    adapter = SRTMAdapter(mode="airgapped")
    adapter.get_elevation = lambda lat, lon: 10.0  # type: ignore[assignment]
    los = adapter.check_line_of_sight((0.0, 0.0), (0.0, 1.0), height_a_m=20.0, height_b_m=20.0)
    assert los["visible"] is True


def test_void_handling(tmp_path: Path) -> None:
    size = 1201
    values = array("h", [-32768] * (size * size))
    values.byteswap()
    p = tmp_path / "void.hgt"
    p.write_bytes(values.tobytes())
    grid = SRTMNormalizer().read_hgt_tile(str(p))
    assert grid[0][0] is None


def test_saudi_tile_range() -> None:
    cfg = SRTMConfig().saudi_tile_range
    assert cfg["lat_range"] == (15, 33)
    assert cfg["lon_range"] == (34, 57)


def test_fetch_airgapped_from_cache(tmp_path: Path) -> None:
    adapter = SRTMAdapter(mode="airgapped")
    adapter.cache_dir = tmp_path
    (tmp_path / "N24E046.hgt").write_bytes(b"x")
    assert "N24E046.hgt" in adapter.get_cached_tiles()
