"""Central radar management and sensor fusion bridge.

Military context:
This is the Krechet-equivalent radar integration point. All registered radars
feed through here: raw plots are parsed, converted to Cartesian, classified
by RCS, correlated across scans, and output as standard SensorReadings into
the existing SensorManager for EKF track fusion.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.adapters.generic_2d_radar import Generic2DRadarAdapter
from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter
from services.radar.adapters.rps82_adapter import RPS82Adapter
from services.radar.adapters.rps202_adapter import RPS202Adapter
from services.radar.adapters.western_aesa_adapter import WesternAESAAdapter
from services.radar.coordinate_converter import CoordinateConverter
from services.radar.models import RadarConfig, RadarPlot, RadarStatus, RadarType
from services.radar.noise_model import RadarNoiseModel
from services.radar.plot_correlator import PlotCorrelator
from services.radar.rcs_classifier import RCSClassifier
from src.sensor_fusion.models import SensorType
from src.sensor_fusion.sensor_manager import SensorManager


ADAPTER_REGISTRY: Dict[RadarType, Type[BaseRadarAdapter]] = {
    RadarType.RPS_82: RPS82Adapter,
    RadarType.RPS_202: RPS202Adapter,
    RadarType.GENERIC_2D: Generic2DRadarAdapter,
    RadarType.GENERIC_3D: Generic3DRadarAdapter,
    RadarType.AESA_WESTERN: WesternAESAAdapter,
    RadarType.AESA_PANEL: WesternAESAAdapter,
}


class RadarManager:
    """Central manager bridging heterogeneous radars to S3M sensor fusion."""

    def __init__(self, sensor_manager: Optional[SensorManager] = None) -> None:
        self._lock = threading.RLock()
        self._radars: Dict[str, RadarConfig] = {}
        self._adapters: Dict[str, BaseRadarAdapter] = {}
        self._status: Dict[str, RadarStatus] = {}
        self._correlators: Dict[str, PlotCorrelator] = {}

        self.converter = CoordinateConverter()
        self.classifier = RCSClassifier()
        self.noise_model = RadarNoiseModel()
        self.sensor_manager = sensor_manager or SensorManager()

    def register_radar(self, config: RadarConfig) -> RadarConfig:
        """Register a radar and create its typed adapter."""
        if not isinstance(config, RadarConfig):
            raise ValueError("config must be a RadarConfig instance")

        adapter_cls = ADAPTER_REGISTRY.get(config.radar_type)
        if adapter_cls is None:
            adapter_cls = Generic3DRadarAdapter  # Fallback

        adapter = adapter_cls(config)

        with self._lock:
            self._radars[config.radar_id] = config
            self._adapters[config.radar_id] = adapter
            self._status[config.radar_id] = RadarStatus(radar_id=config.radar_id)
            self._correlators[config.radar_id] = PlotCorrelator()

            # Tactical bridge: register each radar as a SensorManager feeder
            # so radar detections enter the same fused COP track pipeline.
            self.sensor_manager.register_sensor(
                config.radar_id,
                SensorType.RADAR,
                {
                    "radar_type": config.radar_type.value,
                    "band": config.band.value,
                    "max_range_m": config.max_range_m,
                    "name_en": config.name_en,
                },
            )

        return config

    def remove_radar(self, radar_id: str) -> bool:
        with self._lock:
            removed = self._radars.pop(radar_id, None) is not None
            self._adapters.pop(radar_id, None)
            self._status.pop(radar_id, None)
            self._correlators.pop(radar_id, None)
            return removed

    def ingest_scan(self, radar_id: str, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        """Process a raw radar scan through the full pipeline.

        Pipeline:
        1. Parse raw data via typed adapter
        2. Filter clutter
        3. Convert polar to Cartesian
        4. Classify by RCS
        5. Correlate across scans
        6. Output to SensorManager as SensorReadings
        """
        with self._lock:
            config = self._radars.get(radar_id)
            adapter = self._adapters.get(radar_id)
            status = self._status.get(radar_id)
            correlator = self._correlators.get(radar_id)

        if config is None or adapter is None:
            raise ValueError(f"Radar '{radar_id}' is not registered")

        # Step 1: Parse
        plots = adapter.parse_raw_data(raw_data)

        # Step 2: Filter
        plots = adapter.filter_clutter(plots)

        # Step 3: Convert coordinates
        for plot in plots:
            self.converter.convert_plot(plot, config)

        # Step 4: RCS classification
        self.classifier.classify_plots(plots)

        # Step 5: Plot correlation
        if correlator:
            plots = correlator.correlate(plots)

        # Step 6: Bridge to SensorManager
        for plot in plots:
            if plot.position_cartesian is None:
                continue
            # Compute confidence from noise model
            confidence = self.noise_model.compute_confidence(
                plot.snr_db, plot.range_m, config.max_range_m
            )
            # Map RCS classification to tactical classification string
            classification = RCSClassifier.rcs_class_to_threat_class(plot.rcs_classification)

            self.sensor_manager.ingest(
                sensor_id=radar_id,
                data={
                    "classification": classification,
                    "rcs_dbsm": plot.rcs_dbsm,
                    "rcs_class": plot.rcs_classification.value,
                    "radial_velocity_mps": plot.radial_velocity_mps,
                    "snr_db": plot.snr_db,
                    "plot_id": plot.plot_id,
                    "correlated_track": plot.correlated_track_id,
                },
                position=plot.position_cartesian,
                confidence=confidence,
            )

        # Update status
        with self._lock:
            if status:
                status.scans_received += 1
                status.plots_received += len(plots)
                status.plots_correlated += sum(1 for p in plots if p.correlated_track_id)
                status.last_scan_time = datetime.now(timezone.utc)

        return plots

    def process_fused_tracks(self):
        """Trigger the SensorManager to fuse all pending readings into tracks."""
        return self.sensor_manager.process()

    def get_radar(self, radar_id: str) -> Optional[RadarConfig]:
        with self._lock:
            return self._radars.get(radar_id)

    def list_radars(self) -> List[RadarConfig]:
        with self._lock:
            return list(self._radars.values())

    def get_status(self, radar_id: str) -> Optional[RadarStatus]:
        with self._lock:
            return self._status.get(radar_id)

    def get_all_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                rid: {
                    "operational": s.operational,
                    "scans": s.scans_received,
                    "plots": s.plots_received,
                    "correlated": s.plots_correlated,
                    "last_scan": s.last_scan_time.isoformat() if s.last_scan_time else None,
                }
                for rid, s in self._status.items()
            }

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "registered_radars": len(self._radars),
                "total_scans": sum(s.scans_received for s in self._status.values()),
                "total_plots": sum(s.plots_received for s in self._status.values()),
                "active_correlations": sum(
                    c.get_active_track_count() for c in self._correlators.values()
                ),
            }

