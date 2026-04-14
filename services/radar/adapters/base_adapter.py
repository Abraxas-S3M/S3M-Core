"""Abstract base adapter for tactical radar ingestion.

Military context:
Every hardware-specific adapter must normalize vendor plot formats into one
trusted contract before data enters Layer 02 fusion and engagement planning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from math import exp, floor, sin
from typing import Any, Dict, Iterable, List, Optional

from src.sensor_fusion.models import SensorReading, SensorType
from services.radar.coordinate_converter import CoordinateConverter
from services.radar.models import (
    PlotCorrelation,
    RCSClassification,
    RadarConfig,
    RadarPlot,
    RadarScan,
)
from services.radar.noise_model import RadarNoiseModel
from services.radar.rcs_classifier import RCSClassifier


class BaseRadarAdapter(ABC):
    """Common radar adapter flow: parse, classify, and normalize."""

    def __init__(
        self,
        config: RadarConfig,
        classifier: Optional[RCSClassifier] = None,
        noise_model: Optional[RadarNoiseModel] = None,
    ) -> None:
        self.config = config
        self.classifier = classifier or RCSClassifier()
        self.noise_model = noise_model or RadarNoiseModel.default_for_radar_type(config.radar_type)

    @abstractmethod
    def parse_raw_scan(self, raw_scan: Dict[str, Any]) -> RadarScan:
        """Parse vendor/raw payload into typed RadarScan."""

    def adapt_scan(
        self,
        scan: RadarScan,
        converter: CoordinateConverter,
        correlations: Optional[Iterable[PlotCorrelation]] = None,
    ) -> List[SensorReading]:
        if scan.radar_id != self.config.radar_id:
            raise ValueError(
                f"scan radar_id mismatch: expected {self.config.radar_id}, got {scan.radar_id}"
            )
        correlation_by_plot: Dict[str, PlotCorrelation] = {}
        if correlations:
            for item in correlations:
                correlation_by_plot[item.current_plot_id] = item

        readings: List[SensorReading] = []
        for plot in scan.plots:
            if not self._is_in_range(plot):
                continue
            detection_probability = self._detection_probability(plot)
            if detection_probability <= 0.05:
                continue
            noisy_plot = self._apply_noise(plot)
            position = converter.polar_to_enu(
                range_m=noisy_plot.range_m,
                azimuth_deg=noisy_plot.azimuth_deg,
                elevation_deg=noisy_plot.elevation_deg,
                radar_position_lla=self.config.position_lla,
                orientation_deg=self.config.orientation_deg,
            )
            class_guess = self.classifier.classify(noisy_plot.rcs_m2, noisy_plot.radial_velocity_mps)
            reading = SensorReading(
                sensor_id=self.config.radar_id,
                sensor_type=SensorType.RADAR,
                timestamp=scan.timestamp,
                position=position,
                confidence=detection_probability,
                data=self._build_payload(
                    noisy_plot=noisy_plot,
                    class_guess=class_guess,
                    detection_probability=detection_probability,
                    correlation=correlation_by_plot.get(plot.plot_id),
                ),
            )
            readings.append(reading)
        return readings

    def _is_in_range(self, plot: RadarPlot) -> bool:
        return self.config.min_range_m <= plot.range_m <= self.config.max_range_m

    def _detection_probability(self, plot: RadarPlot) -> float:
        curve = self.config.detection_probability_curve
        from_curve = self._interpolate_curve(plot.snr_db, curve) if curve else self._snr_logistic_probability(plot.snr_db)
        probability = plot.confidence * self.config.nominal_detection_probability * from_curve
        return max(0.0, min(1.0, probability))

    @staticmethod
    def _snr_logistic_probability(snr_db: float) -> float:
        # Tactical default: around 6 dB gives ~0.5 detection probability.
        return 1.0 / (1.0 + exp(-(float(snr_db) - 6.0) / 3.0))

    @staticmethod
    def _interpolate_curve(snr_db: float, curve: Iterable[tuple[float, float]]) -> float:
        points = sorted((float(x), float(y)) for x, y in curve)
        if not points:
            return 1.0
        if snr_db <= points[0][0]:
            return max(0.0, min(1.0, points[0][1]))
        if snr_db >= points[-1][0]:
            return max(0.0, min(1.0, points[-1][1]))
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            if x0 <= snr_db <= x1:
                ratio = 0.0 if x1 == x0 else (snr_db - x0) / (x1 - x0)
                return max(0.0, min(1.0, y0 + ratio * (y1 - y0)))
        return 1.0

    def _apply_noise(self, plot: RadarPlot) -> RadarPlot:
        covariance = self.noise_model.covariance_metadata(self.config, plot.snr_db)
        range_sigma = covariance["sigma_range_m"]
        az_sigma_rad = covariance["sigma_az_rad"]
        el_sigma_rad = covariance["sigma_el_rad"]
        vel_sigma = covariance["sigma_velocity_mps"]

        seed = self._seed_for_plot(plot.plot_id)
        range_noise = self._deterministic_noise(seed, range_sigma)
        az_noise_deg = self._deterministic_noise(seed + 101, az_sigma_rad * 57.29577951308232)
        el_noise_deg = self._deterministic_noise(seed + 211, el_sigma_rad * 57.29577951308232)
        vel_noise = self._deterministic_noise(seed + 307, vel_sigma)

        return RadarPlot(
            plot_id=plot.plot_id,
            timestamp=plot.timestamp,
            range_m=max(0.0, plot.range_m + range_noise),
            azimuth_deg=(plot.azimuth_deg + az_noise_deg) % 360.0,
            elevation_deg=plot.elevation_deg + el_noise_deg,
            radial_velocity_mps=plot.radial_velocity_mps + vel_noise,
            rcs_m2=plot.rcs_m2,
            snr_db=plot.snr_db,
            confidence=plot.confidence,
            metadata=dict(plot.metadata),
        )

    @staticmethod
    def _seed_for_plot(plot_id: str) -> int:
        return sum((idx + 1) * ord(ch) for idx, ch in enumerate(plot_id))

    @staticmethod
    def _deterministic_noise(seed: int, sigma: float) -> float:
        scaled = sin(seed * 12.9898) * 43758.5453
        fractional = scaled - floor(scaled)
        centered = 2.0 * fractional - 1.0
        return centered * float(sigma)

    def _build_payload(
        self,
        noisy_plot: RadarPlot,
        class_guess: RCSClassification,
        detection_probability: float,
        correlation: Optional[PlotCorrelation],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "radar_id": self.config.radar_id,
            "radar_type": self.config.radar_type.value,
            "plot_id": noisy_plot.plot_id,
            "classification": class_guess.value,
            "target_allocator_classification": self.classifier.to_target_allocator_label(class_guess),
            "detection_probability": detection_probability,
            "range_m": noisy_plot.range_m,
            "azimuth_deg": noisy_plot.azimuth_deg,
            "elevation_deg": noisy_plot.elevation_deg,
            "radial_velocity_mps": noisy_plot.radial_velocity_mps,
            "rcs_m2": noisy_plot.rcs_m2,
            "snr_db": noisy_plot.snr_db,
            "noise_covariance": self.noise_model.measurement_covariance(self.config, noisy_plot.snr_db),
        }
        if correlation is not None:
            payload["plot_correlation"] = {
                "correlation_id": correlation.correlation_id,
                "previous_plot_id": correlation.previous_plot_id,
                "score": correlation.score,
                "distance_m": correlation.spatial_distance_m,
                "velocity_delta_mps": correlation.radial_velocity_delta_mps,
            }
        return payload
