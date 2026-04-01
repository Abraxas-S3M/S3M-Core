"""Satellite image processing utilities for maritime surveillance workflows."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional

import numpy as np

from services.sensor_analytics.models import SARDetection, SARImageMeta


class SatelliteImageProcessor:
    """Process SAR and optical satellite imagery for maritime awareness."""

    def __init__(self) -> None:
        self._last_error: Optional[str] = None

    def _load_array(self, filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Satellite image not found: {filepath}")
        try:
            from PIL import Image  # type: ignore

            img = Image.open(filepath)
            arr = np.array(img)
            return {"array": arr, "channels": arr.shape[2] if arr.ndim == 3 else 1}
        except Exception:
            pass

        try:
            import tifffile  # type: ignore

            arr = tifffile.imread(filepath)
            return {"array": np.array(arr), "channels": arr.shape[2] if arr.ndim == 3 else 1}
        except Exception:
            pass

        try:
            arr = np.fromfile(filepath, dtype=np.uint8)
            if arr.size == 0:
                raise ValueError("Empty file")
            side = int(np.sqrt(arr.size))
            arr = arr[: side * side].reshape(side, side)
            return {"array": arr, "channels": 1}
        except Exception as exc:
            self._last_error = str(exc)
            return {"array": None, "channels": 0}

    def load_sentinel1(self, filepath: str) -> Dict[str, Any]:
        """Load Sentinel-1 SAR file into ndarray with basic metadata."""
        loaded = self._load_array(filepath)
        arr = loaded["array"]
        if arr is None:
            return {"array": None, "meta": None}
        h, w = arr.shape[:2]
        meta = SARImageMeta(
            image_id=os.path.basename(filepath),
            source="sentinel-1",
            filepath=filepath,
            width=int(w),
            height=int(h),
            acquisition_time=datetime.now(timezone.utc),
            polarization="VV",
            resolution_meters=10.0,
            center_lat=25.0,
            center_lon=50.0,
            bounds={"north": 26.0, "south": 24.0, "east": 51.0, "west": 49.0},
            metadata={"channels": loaded["channels"]},
        )
        return {"array": arr, "meta": meta}

    def load_sentinel2(self, filepath: str) -> Dict[str, Any]:
        """Load Sentinel-2 optical imagery into ndarray."""
        loaded = self._load_array(filepath)
        arr = loaded["array"]
        if arr is None:
            return {"array": None, "meta": None}
        h, w = arr.shape[:2]
        meta = SARImageMeta(
            image_id=os.path.basename(filepath),
            source="local",
            filepath=filepath,
            width=int(w),
            height=int(h),
            acquisition_time=datetime.now(timezone.utc),
            polarization="VV",
            resolution_meters=10.0,
            center_lat=25.0,
            center_lon=50.0,
            bounds={"north": 26.0, "south": 24.0, "east": 51.0, "west": 49.0},
            metadata={"channels": loaded["channels"], "sensor": "sentinel-2"},
        )
        return {"array": arr, "meta": meta}

    def compute_ship_mask(self, sar_array, threshold: float = 0.7):
        """Simple CFAR-like detector using local mean over 50x50 windows."""
        arr = np.asarray(sar_array, dtype=np.float32)
        if arr.ndim == 3:
            arr = arr.mean(axis=2)
        h, w = arr.shape
        mask = np.zeros((h, w), dtype=np.uint8)
        radius = 25
        # Maritime context: bright scatterers in SAR can indicate metallic hulls.
        for y in range(h):
            y0 = max(0, y - radius)
            y1 = min(h, y + radius + 1)
            for x in range(w):
                x0 = max(0, x - radius)
                x1 = min(w, x + radius + 1)
                window = arr[y0:y1, x0:x1]
                background = float(window.mean()) if window.size else 0.0
                if background <= 0:
                    continue
                if arr[y, x] > background * (1.0 + float(threshold)):
                    mask[y, x] = 1
        return mask

    def extract_chips(self, image_array, detections: List[SARDetection], chip_size: int = 128) -> List[Dict[str, Any]]:
        arr = np.asarray(image_array)
        h, w = arr.shape[:2]
        half = max(1, chip_size // 2)
        chips: List[Dict[str, Any]] = []
        for det in detections:
            x_min, y_min, x_max, y_max = det.bbox
            cx = int((x_min + x_max) / 2.0)
            cy = int((y_min + y_max) / 2.0)
            x0 = max(0, cx - half)
            y0 = max(0, cy - half)
            x1 = min(w, cx + half)
            y1 = min(h, cy + half)
            chip = arr[y0:y1, x0:x1]
            chips.append({"detection_id": det.detection_id, "chip": chip, "bbox": (x0, y0, x1, y1)})
        return chips

    def get_coverage_area(self, image_meta: SARImageMeta) -> float:
        width_m = float(image_meta.width) * float(image_meta.resolution_meters)
        height_m = float(image_meta.height) * float(image_meta.resolution_meters)
        return (width_m * height_m) / 1_000_000.0

    def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "last_error": self._last_error}

