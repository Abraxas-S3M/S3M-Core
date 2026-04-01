#!/usr/bin/env python3
"""Tests for SARDetector backends and detection flow."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from services.sensor_analytics.sar.detector import SARDetector


def _make_image(path: Path) -> None:
    arr = np.zeros((128, 128), dtype=np.uint8)
    arr[20:25, 20:25] = 255
    Image.fromarray(arr).save(path)


def test_sar_detector_initializes_stub_if_no_model() -> None:
    detector = SARDetector(model_backend="auto")
    info = detector.get_model_info()
    assert "backend" in info
    assert info["backend"] in {"stub", "phase5_yolo", "yolov8", "ultralytics", "onnx"}


def test_detect_returns_list(tmp_path: Path) -> None:
    image_path = tmp_path / "sar.png"
    _make_image(image_path)
    detector = SARDetector(model_backend="stub")
    detections = detector.detect(str(image_path))
    assert isinstance(detections, list)


def test_detect_batch_processes_multiple_paths(tmp_path: Path) -> None:
    path1 = tmp_path / "a.png"
    path2 = tmp_path / "b.png"
    _make_image(path1)
    _make_image(path2)
    detector = SARDetector(model_backend="stub")
    output = detector.detect_batch([str(path1), str(path2)])
    assert set(output.keys()) == {"a", "b"}


def test_get_model_info_has_backend_fields() -> None:
    detector = SARDetector(model_backend="stub")
    info = detector.get_model_info()
    assert "backend" in info
    assert "input_shape" in info
