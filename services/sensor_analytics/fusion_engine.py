"""Maritime fusion engine for Layer 09 wide-area surveillance."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.sensor_analytics.ais import AISAnomalyDetector, AISTracker
from services.sensor_analytics.border import BorderSurveillanceEngine
from services.sensor_analytics.geospatial import GeospatialProcessor
from services.sensor_analytics.models import MaritimePicture, SARDetection, VesselClassification
from services.sensor_analytics.sar import SARDetector, SARShipClassifier
from src.sensor_fusion.models import SensorType
from src.sensor_fusion.sensor_manager import SensorManager
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource
from src.threat_detection.threat_manager import ThreatManager


class MaritimeFusionEngine:
    """Fuse SAR, AIS, and border analytics into one operational picture."""

    def __init__(self) -> None:
        self.sar_detector = SARDetector()
        self.ais_tracker = AISTracker()
        self.ais_anomaly = AISAnomalyDetector()
        self.border_engine = BorderSurveillanceEngine(
            ais_tracker=self.ais_tracker,
            sar_detector=self.sar_detector,
            ais_anomaly_detector=self.ais_anomaly,
        )
        self.geo = GeospatialProcessor()
        self.classifier = SARShipClassifier()
        self.threat_manager = ThreatManager()
        self.sensor_manager = SensorManager()
        self._latest_picture: Optional[MaritimePicture] = None
        self._unmatched_sar: List[SARDetection] = []
        self.latest_unmatched_sar: List[SARDetection] = []
        self.latest_alerts: List[Dict[str, Any]] = []
        self._threat_events: List[ThreatEvent] = []

        try:
            self.sensor_manager.register_sensor(
                sensor_id="satellite-feed",
                sensor_type=SensorType.RADAR,
                config={"layer": "09", "context": "satellite_maritime"},
            )
        except Exception:
            pass

    def fuse(
        self, sar_detections: Optional[List[SARDetection]] = None, ais_data_path: Optional[str] = None
    ) -> MaritimePicture:
        if ais_data_path:
            self.ais_tracker.ingest_file(ais_data_path)
        if sar_detections is None:
            sar_detections = []
        self._unmatched_sar = []

        for det in sar_detections:
            match = self.ais_tracker.match_sar_detection(det)
            if match is None:
                self._unmatched_sar.append(det)
            else:
                match.last_position = det.geo_position
                match.length_meters = det.estimated_length_meters or match.length_meters
                match.beam_meters = det.estimated_width_meters or match.beam_meters

        all_vessels = self.ais_tracker.get_all_vessels()
        anomalies: List[Dict[str, Any]] = []
        alerts: List[Dict[str, Any]] = []
        for vessel in all_vessels:
            vessel_anomalies = self.ais_anomaly.detect_anomalies(vessel)
            anomalies.extend(vessel_anomalies)
            alerts.extend([a.to_dict() for a in self.ais_anomaly.to_border_alerts(vessel_anomalies, vessel)])

        for dark_det in self._unmatched_sar:
            alerts.append(
                {
                    "alert_id": f"dark-{dark_det.detection_id}",
                    "zone_id": "UNASSIGNED",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "alert_type": "dark_vessel",
                    "severity": "high",
                    "position": dark_det.geo_position,
                    "description": "Unmatched SAR detection indicating potential dark vessel.",
                    "vessel_id": None,
                    "confidence": dark_det.confidence,
                    "evidence": [dark_det.to_dict()],
                }
            )
            self._threat_events.append(
                ThreatEvent(
                    source=ThreatSource.SENSOR_FUSION,
                    level=ThreatLevel.HIGH,
                    category=ThreatCategory.KINETIC,
                    title="Dark vessel candidate from SAR",
                    description="Satellite SAR detected vessel-sized return without AIS correlation.",
                    raw_data=dark_det.to_dict(),
                    confidence=dark_det.confidence,
                    location={"lat": dark_det.geo_position[0], "lon": dark_det.geo_position[1]},
                    recommended_action="Task maritime ISR and intercept assets for identification.",
                )
            )

        self.latest_unmatched_sar = list(self._unmatched_sar)
        self.latest_alerts = list(alerts)

        for vessel in all_vessels:
            lat, lon = vessel.last_position
            self.sensor_manager.ingest(
                sensor_id="satellite-feed",
                data={"x": lon * 1000.0, "y": lat * 1000.0, "z": 0.0, "mmsi": vessel.mmsi},
                position=(lon * 1000.0, lat * 1000.0, 0.0),
                confidence=max(0.2, min(1.0, 1.0 - vessel.risk_score / 2.0)),
            )
        self.sensor_manager.process()

        zones = [z.to_dict() for z in self.border_engine.zone_manager.get_zones()]
        vessels_payload = [v.to_dict() for v in all_vessels]
        stats = self.ais_tracker.get_statistics()
        stats.update(
            {
                "anomalies": len(anomalies),
                "alerts_active": len(alerts),
                "unmatched_sar": len(self._unmatched_sar),
            }
        )

        self._latest_picture = MaritimePicture(
            timestamp=datetime.now(timezone.utc),
            region="all",
            vessels=vessels_payload,
            sar_detections=[d.to_dict() for d in self._unmatched_sar],
            border_alerts=alerts,
            zones=zones,
            statistics=stats,
        )
        return self._latest_picture

    def process_sar_image(self, image_path: str) -> Dict[str, Any]:
        detections = self.sar_detector.detect(image_path)
        matched = 0
        for det in detections:
            classification = self.classifier.classify(det)
            if classification == VesselClassification.UNKNOWN:
                pass
            if self.ais_tracker.match_sar_detection(det):
                matched += 1
        picture = self.fuse(sar_detections=detections)
        return {
            "detections": len(detections),
            "matched": matched,
            "dark_vessels": len(detections) - matched,
            "alerts": len(picture.border_alerts),
            "picture": picture,
        }

    def get_maritime_picture(self) -> MaritimePicture:
        if self._latest_picture is None:
            return self.fuse()
        return self._latest_picture

    def get_dark_vessels(self) -> List[Dict[str, Any]]:
        dark_ais = [
            vessel.to_dict()
            for vessel in self.ais_tracker.get_dark_vessels()
        ]
        sar_dark = [
            det.to_dict()
            for det in self._unmatched_sar
        ]
        return sar_dark + dark_ais

    def export_picture(self, filepath: str, format: str = "geojson") -> None:
        picture = self.get_maritime_picture()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        if format.lower() != "geojson":
            raise ValueError("Only geojson export is supported.")
        features: List[Dict[str, Any]] = []
        for vessel in picture.vessels:
            pos = vessel.get("last_position", (0.0, 0.0))
            lat, lon = float(pos[0]), float(pos[1])
            features.append(
                self.geo.create_geojson_feature(
                    (lat, lon),
                    {"entity": "vessel", "mmsi": vessel.get("mmsi"), "classification": vessel.get("classification")},
                    geometry_type="Point",
                )
            )
        for detection in picture.sar_detections:
            lat, lon = detection.get("geo_position", (0.0, 0.0))
            features.append(
                self.geo.create_geojson_feature(
                    (lat, lon),
                    {"entity": "sar_detection", "detection_id": detection.get("detection_id")},
                    geometry_type="Point",
                )
            )
        self.geo.export_geojson(features, filepath)

    def health_check(self) -> Dict[str, Any]:
        return {
            "sar": self.sar_detector.health_check(),
            "ais": self.ais_tracker.get_statistics(),
            "border": self.border_engine.health_check(),
            "picture_ready": self._latest_picture is not None,
        }
