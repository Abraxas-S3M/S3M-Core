"""Central radar manager for multi-radar tactical integration.

Military context:
This manager emulates a Krechet-like integration node by accepting multiple
radar types, normalizing plots, and pushing unified readings into Layer 02.
"""

from __future__ import annotations

from dataclasses import asdict
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple, Union

from src.sensor_fusion.models import SensorReading, SensorType
from src.sensor_fusion.sensor_manager import SensorManager
from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.adapters.generic_2d_radar import Generic2DRadarAdapter
from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter
from services.radar.adapters.rps82_adapter import RPS82Adapter
from services.radar.adapters.rps202_adapter import RPS202Adapter
from services.radar.adapters.western_aesa_adapter import WesternAESAAdapter
from services.radar.coordinate_converter import CoordinateConverter
from services.radar.models import PlotCorrelation, RadarConfig, RadarScan, RadarType
from services.radar.plot_correlator import PlotCorrelator


class RadarManager:
    """Register radar adapters and ingest normalized sensor readings."""

    def __init__(
        self,
        sensor_manager: Optional[SensorManager] = None,
        reference_origin_lla: Optional[Tuple[float, float, float]] = None,
    ) -> None:
        self._lock = RLock()
        self._sensor_manager = sensor_manager or SensorManager()
        self._reference_origin_lla = reference_origin_lla
        self._adapters: Dict[str, BaseRadarAdapter] = {}
        self._configs: Dict[str, RadarConfig] = {}
        self._plot_correlator = PlotCorrelator()

    def register_radar(self, config: RadarConfig) -> None:
        with self._lock:
            if config.radar_id in self._adapters:
                raise ValueError(f"Radar '{config.radar_id}' is already registered")
            adapter = self._build_adapter(config)
            self._adapters[config.radar_id] = adapter
            self._configs[config.radar_id] = config
            if self._reference_origin_lla is None:
                self._reference_origin_lla = config.position_lla
            self._sensor_manager.register_sensor(
                sensor_id=config.radar_id,
                sensor_type=SensorType.RADAR,
                config=self._serialize_config(config),
            )

    def unregister_radar(self, radar_id: str) -> bool:
        with self._lock:
            removed = radar_id in self._adapters
            if not removed:
                return False
            del self._adapters[radar_id]
            del self._configs[radar_id]
            self._plot_correlator.clear(radar_id=radar_id)
            return True

    def ingest_scan(self, radar_id: str, scan_input: Union[Dict[str, Any], RadarScan]) -> List[SensorReading]:
        with self._lock:
            adapter = self._adapters.get(radar_id)
            if adapter is None:
                raise ValueError(f"Radar '{radar_id}' is not registered")
            scan = scan_input if isinstance(scan_input, RadarScan) else adapter.parse_raw_scan(scan_input)
            correlations = self._plot_correlator.correlate(scan)
            converter = self._build_converter()
            normalized_readings = adapter.adapt_scan(scan=scan, converter=converter, correlations=correlations)
            ingested: List[SensorReading] = []
            for reading in normalized_readings:
                ingested_reading = self._sensor_manager.ingest(
                    sensor_id=reading.sensor_id,
                    data=dict(reading.data),
                    position=reading.position,
                    confidence=reading.confidence,
                )
                ingested.append(ingested_reading)
            return ingested

    def ingest_scan_with_correlations(
        self,
        radar_id: str,
        scan_input: Union[Dict[str, Any], RadarScan],
    ) -> Tuple[List[SensorReading], List[PlotCorrelation]]:
        with self._lock:
            adapter = self._adapters.get(radar_id)
            if adapter is None:
                raise ValueError(f"Radar '{radar_id}' is not registered")
            scan = scan_input if isinstance(scan_input, RadarScan) else adapter.parse_raw_scan(scan_input)
            correlations = self._plot_correlator.correlate(scan)
            converter = self._build_converter()
            normalized_readings = adapter.adapt_scan(scan=scan, converter=converter, correlations=correlations)
            ingested: List[SensorReading] = []
            for reading in normalized_readings:
                ingested.append(
                    self._sensor_manager.ingest(
                        sensor_id=reading.sensor_id,
                        data=dict(reading.data),
                        position=reading.position,
                        confidence=reading.confidence,
                    )
                )
            return ingested, correlations

    def process_fusion(self):
        with self._lock:
            return self._sensor_manager.process()

    def get_registered_radars(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._serialize_config(cfg) for cfg in self._configs.values()]

    def get_sensor_manager(self) -> SensorManager:
        return self._sensor_manager

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "registered_radars": len(self._adapters),
                "radar_ids": sorted(self._adapters.keys()),
                "reference_origin_lla": self._reference_origin_lla,
                "sensor_manager": self._sensor_manager.health_check(),
            }

    def _build_converter(self) -> CoordinateConverter:
        if self._reference_origin_lla is None:
            raise RuntimeError("No reference origin configured; register at least one radar")
        return CoordinateConverter(
            reference_latitude_deg=self._reference_origin_lla[0],
            reference_longitude_deg=self._reference_origin_lla[1],
            reference_altitude_m=self._reference_origin_lla[2],
        )

    @staticmethod
    def _serialize_config(config: RadarConfig) -> Dict[str, Any]:
        payload = asdict(config)
        payload["radar_type"] = config.radar_type.value
        payload["radar_band"] = config.radar_band.value
        payload["status"] = config.status.value
        payload["position_lla"] = tuple(config.position_lla)
        payload["orientation_deg"] = tuple(config.orientation_deg)
        return payload

    @staticmethod
    def _build_adapter(config: RadarConfig) -> BaseRadarAdapter:
        factory = {
            RadarType.GENERIC_2D: Generic2DRadarAdapter,
            RadarType.GENERIC_3D: Generic3DRadarAdapter,
            RadarType.RPS_82: RPS82Adapter,
            RadarType.RPS_202: RPS202Adapter,
            RadarType.WESTERN_AESA: WesternAESAAdapter,
        }
        adapter_cls = factory[config.radar_type]
        return adapter_cls(config)
