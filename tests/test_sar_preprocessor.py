from __future__ import annotations

import numpy as np

from services.sensor_analytics.models import SARImageMeta
from services.sensor_analytics.sar.preprocessor import SARPreprocessor


def test_despeckle_lee_filter_returns_same_shape():
    pre = SARPreprocessor()
    rng = np.random.default_rng(42)
    noisy = (rng.random((32, 32)) * 255).astype(np.float32)
    out = pre.despeckle(noisy, method="lee")
    assert out.shape == noisy.shape


def test_normalize_scales_to_uint8():
    pre = SARPreprocessor()
    arr = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)
    norm = pre.normalize(arr)
    assert norm.dtype == np.uint8
    assert int(norm.min()) == 0
    assert int(norm.max()) == 255


def test_tile_image_expected_count():
    pre = SARPreprocessor()
    arr = np.zeros((1280, 1280), dtype=np.uint8)
    tiles = pre.tile_image(arr, tile_size=640, overlap=64)
    assert len(tiles) == 9


def test_pixel_to_geo_conversion():
    pre = SARPreprocessor()
    meta = SARImageMeta(
        image_id="img",
        source="sentinel-1",
        filepath="x",
        width=1000,
        height=1000,
        acquisition_time=np.datetime64("2026-01-01").astype(object),
        polarization="VV",
        resolution_meters=10.0,
        center_lat=25.0,
        center_lon=50.0,
        bounds={"north": 26.0, "south": 24.0, "east": 51.0, "west": 49.0},
        metadata={},
    )
    lat, lon = pre.pixel_to_geo(500, 500, meta)
    assert abs(lat - 25.0) < 1e-6
    assert abs(lon - 50.0) < 1e-6
