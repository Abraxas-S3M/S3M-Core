"""Noise and confidence utilities for radar track ingestion."""

from __future__ import annotations


class RadarNoiseModel:
    """Estimate normalized confidence from SNR and range geometry."""

    def compute_confidence(self, snr_db: float, range_m: float, max_range_m: float) -> float:
        if not isinstance(snr_db, (int, float)):
            raise ValueError("snr_db must be numeric")
        if not isinstance(range_m, (int, float)) or float(range_m) < 0.0:
            raise ValueError("range_m must be a non-negative number")
        if not isinstance(max_range_m, (int, float)) or float(max_range_m) <= 0.0:
            raise ValueError("max_range_m must be a positive number")

        snr_norm = max(0.0, min(1.0, (float(snr_db) + 10.0) / 40.0))
        range_norm = max(0.0, min(1.0, float(range_m) / float(max_range_m)))

        # Tactical weighting: signal quality drives trust more than range
        # because EW environments can distort distant weak returns.
        confidence = (0.7 * snr_norm) + (0.3 * (1.0 - range_norm))
        return max(0.0, min(1.0, confidence))

