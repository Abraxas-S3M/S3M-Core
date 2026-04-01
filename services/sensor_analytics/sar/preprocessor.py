"""SAR image preprocessing utilities for wide-area maritime surveillance."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from services.sensor_analytics.models import SARImageMeta


class SARPreprocessor:
    """Preprocess SAR imagery for ship detection in tactical workflows."""

    def __init__(self) -> None:
        self.numpy_available = True

    def load_image(self, filepath: str) -> Dict[str, Any]:
        if not isinstance(filepath, str) or not filepath.strip():
            return {"filepath": filepath, "loaded": False, "reason": "invalid filepath"}

        try:
            from PIL import Image  # type: ignore

            with Image.open(filepath) as img:
                arr = np.array(img)
                if arr.ndim == 2:
                    channels = 1
                elif arr.ndim == 3:
                    channels = int(arr.shape[2])
                else:
                    channels = 1
                return {
                    "array": arr,
                    "width": int(arr.shape[1]),
                    "height": int(arr.shape[0]),
                    "channels": channels,
                    "metadata": {"loader": "PIL", "mode": getattr(img, "mode", "unknown")},
                    "loaded": True,
                }
        except Exception:
            pass

        try:
            import tifffile  # type: ignore

            arr = tifffile.imread(filepath)
            if arr.ndim == 2:
                channels = 1
            elif arr.ndim == 3:
                channels = int(arr.shape[2])
            else:
                channels = 1
            return {
                "array": arr,
                "width": int(arr.shape[1]),
                "height": int(arr.shape[0]),
                "channels": channels,
                "metadata": {"loader": "tifffile"},
                "loaded": True,
            }
        except Exception:
            pass

        return {"filepath": filepath, "loaded": False, "reason": "no image library"}

    def despeckle(self, image_array: np.ndarray, method: str = "lee") -> np.ndarray:
        if method == "none":
            return image_array
        if method == "median":
            return self._median_filter(image_array)
        if method != "lee":
            return image_array
        return self._lee_filter(image_array)

    def _lee_filter(self, image_array: np.ndarray, kernel_size: int = 5) -> np.ndarray:
        if image_array is None:
            return image_array
        if image_array.ndim == 3:
            # Tactical assumption: convert multi-channel imagery to intensity.
            working = image_array.mean(axis=2)
        else:
            working = image_array

        arr = working.astype(np.float32)
        pad = kernel_size // 2
        padded = np.pad(arr, ((pad, pad), (pad, pad)), mode="reflect")
        out = np.zeros_like(arr, dtype=np.float32)
        noise_var = float(np.var(arr)) * 0.25 + 1e-9

        for y in range(arr.shape[0]):
            for x in range(arr.shape[1]):
                win = padded[y : y + kernel_size, x : x + kernel_size]
                local_mean = float(np.mean(win))
                local_var = float(np.var(win))
                weight = local_var / (local_var + noise_var)
                out[y, x] = local_mean + weight * (arr[y, x] - local_mean)
        return out

    def _median_filter(self, image_array: np.ndarray, kernel_size: int = 3) -> np.ndarray:
        if image_array.ndim == 3:
            working = image_array.mean(axis=2)
        else:
            working = image_array
        arr = working.astype(np.float32)
        pad = kernel_size // 2
        padded = np.pad(arr, ((pad, pad), (pad, pad)), mode="reflect")
        out = np.zeros_like(arr, dtype=np.float32)
        for y in range(arr.shape[0]):
            for x in range(arr.shape[1]):
                win = padded[y : y + kernel_size, x : x + kernel_size]
                out[y, x] = float(np.median(win))
        return out

    def normalize(self, image_array: np.ndarray) -> np.ndarray:
        arr = image_array.astype(np.float32)
        min_v = float(np.min(arr))
        max_v = float(np.max(arr))
        if max_v - min_v < 1e-9:
            return np.zeros_like(arr, dtype=np.uint8)
        scaled = (arr - min_v) / (max_v - min_v)
        return np.clip(scaled * 255.0, 0, 255).astype(np.uint8)

    def tile_image(self, image_array: np.ndarray, tile_size: int = 640, overlap: int = 64) -> List[Dict[str, Any]]:
        h = int(image_array.shape[0])
        w = int(image_array.shape[1])
        stride = max(1, tile_size - overlap)
        tiles: List[Dict[str, Any]] = []

        y = 0
        while y < h:
            x = 0
            while x < w:
                y2 = min(y + tile_size, h)
                x2 = min(x + tile_size, w)
                tile = image_array[y:y2, x:x2]
                tiles.append({"array": tile, "offset_x": x, "offset_y": y, "tile_size": tile_size})
                if x + tile_size >= w:
                    break
                x += stride
            if y + tile_size >= h:
                break
            y += stride
        return tiles

    def pixel_to_geo(self, pixel_x: float, pixel_y: float, image_meta: SARImageMeta) -> tuple[float, float]:
        north = float(image_meta.bounds.get("north", image_meta.center_lat))
        south = float(image_meta.bounds.get("south", image_meta.center_lat))
        west = float(image_meta.bounds.get("west", image_meta.center_lon))
        east = float(image_meta.bounds.get("east", image_meta.center_lon))

        x_ratio = float(pixel_x) / max(float(image_meta.width), 1.0)
        y_ratio = float(pixel_y) / max(float(image_meta.height), 1.0)

        lon = west + x_ratio * (east - west)
        lat = north - y_ratio * (north - south)
        return (lat, lon)
