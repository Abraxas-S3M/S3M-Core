"""Border surveillance engine integrating AIS and SAR maritime monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.sensor_analytics.ais.anomaly_detector import AISAnomalyDetector
from services.sensor_analytics.ais.tracker import AISTracker
from services.sensor_analytics.border.zone_manager import ZoneManager
from services.sensor_analytics.models import BorderAlert, BorderZone, MaritimePicture, SARDetection
from services.sensor_analytics.sar.detector import SARDetector
from src.sensor_fusion.models import SensorType
from src.sensor_fusion.sensor_manager import SensorManager
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource
from src.threat_detection.threat_manager import ThreatManager


class BorderSurveillanceEngine:
    """Create zone-focused maritime alerts for tactical command workflows."""

    def __init__(
        self,
        ais_tracker: Optional[AISTracker] = None,
        sar_detector: Optional[SARDetector] = None,
        ais_anomaly_detector: Optional[AISAnomalyDetector] = None,
        zone_manager: Optional[ZoneManager] = None,
        threat_manager: Optional[ThreatManager] = None,
        sensor_manager: Optional[SensorManager] = None,
    ) -> None:
        self.zone_manager = zone_manager or ZoneManager()
        self.ais_tracker = ais_tracker or AISTracker()
        self.sar_detector = sar_detector or SARDetector()
        self.anomaly_detector = ais_anomaly_detector or AISAnomalyDetector()
        self.anomaly_detector.set_restricted_zones(self.zone_manager.get_zones())
        self.threat_manager = threat_manager or ThreatManager()
        self.sensor_manager = sensor_manager or SensorManager()
        self.active_alerts: List[BorderAlert] = []

        try:
            self.sensor_manager.register_sensor(
                "satellite-maritime",
                SensorType.RADAR,
                {"source": "sensor_analytics", "domain": "maritime"},
            )
        except Exception:
            pass

    def scan_zone(self, zone: BorderZone) -> List[BorderAlert]:
        zone_alerts: List[BorderAlert] = []
        vessels = self.ais_tracker.get_vessels_in_zone(zone)
        for vessel in vessels:
            anomalies = self.anomaly_detector.detect_anomalies(vessel)
            zone_alerts.extend(self.anomaly_detector.to_border_alerts(anomalies, vessel))
        for vessel in self.ais_tracker.get_dark_vessels():
            lat, lon = vessel.last_position
            if zone.contains_point(lat, lon):
                zone_alerts.append(
                    BorderAlert(
                        alert_id=f"dark-{vessel.mmsi}-{int(datetime.now(timezone.utc).timestamp())}",
                        zone_id=zone.zone_id,
                        timestamp=datetime.now(timezone.utc),
                        alert_type="dark_vessel",
                        severity="high",
                        position=vessel.last_position,
                        description=(
                            "AIS transmission gap indicates potential dark vessel behavior in maritime zone."
                        ),
                        vessel_id=vessel.mmsi,
                        confidence=0.85,
                        evidence=[{"risk_score": vessel.risk_score}],
                    )
                )
        self.active_alerts.extend(zone_alerts)
        self.active_alerts = self.active_alerts[-5000:]
        return zone_alerts

    def scan_all_zones(self) -> Dict[str, List[BorderAlert]]:
        result: Dict[str, List[BorderAlert]] = {}
        for zone in self.zone_manager.get_zones():
            result[zone.zone_id] = self.scan_zone(zone)
        return result

    def process_sar_sweep(self, image_path: str) -> List[BorderAlert]:
        detections = self.sar_detector.detect(image_path)
        alerts: List[BorderAlert] = []
        for detection in detections:
            vessel = self.ais_tracker.match_sar_detection(detection)
            if vessel:
                continue
            lat, lon = detection.geo_position
            zones = self.zone_manager.check_position(lat, lon)
            zone_id = zones[0].zone_id if zones else "UNASSIGNED"
            alerts.append(
                BorderAlert(
                    alert_id=f"sar-dark-{detection.detection_id}",
                    zone_id=zone_id,
                    timestamp=datetime.now(timezone.utc),
                    alert_type="dark_vessel",
                    severity="high",
                    position=detection.geo_position,
                    description=(
                        "Unmatched SAR vessel contact suggests transponder-silent vessel in surveillance sector."
                    ),
                    vessel_id=None,
                    confidence=max(0.6, detection.confidence),
                    evidence=[detection.to_dict()],
                )
            )
        self.active_alerts.extend(alerts)
        self.active_alerts = self.active_alerts[-5000:]
        return alerts

    def feed_to_threat_detection(self, alerts: List[BorderAlert]) -> List[ThreatEvent]:
        events: List[ThreatEvent] = []
        for alert in alerts:
            if alert.alert_type == "dark_vessel":
                category = ThreatCategory.KINETIC
                level = ThreatLevel.HIGH
            elif alert.alert_type == "zone_intrusion":
                category = ThreatCategory.SURVEILLANCE
                level = ThreatLevel.MEDIUM
            else:
                category = ThreatCategory.SURVEILLANCE
                level = ThreatLevel.LOW

            event = ThreatEvent(
                source=ThreatSource.SENSOR_FUSION,
                level=level,
                category=category,
                title=f"Border alert: {alert.alert_type}",
                description=alert.description,
                raw_data=alert.to_dict(),
                confidence=alert.confidence,
                location={"lat": alert.position[0], "lon": alert.position[1]},
                asset_ids=[alert.zone_id] if alert.zone_id else [],
                recommended_action=(
                    "Task nearest maritime ISR asset and maintain continuous tracking until identity confirmed."
                ),
            )
            self.threat_manager._threat_log.append(event)  # noqa: SLF001
            events.append(event)
        return events

    def _feed_positions_to_sensor_manager(self) -> None:
        for vessel in self.ais_tracker.get_all_vessels():
            lat, lon = vessel.last_position
            try:
                self.sensor_manager.ingest(
                    sensor_id="satellite-maritime",
                    data={
                        "x": lon * 1000.0,
                        "y": lat * 1000.0,
                        "z": 0.0,
                        "lat": lat,
                        "lon": lon,
                        "speed_knots": vessel.last_speed_knots,
                        "classification": vessel.classification.value,
                        "source": "satellite",
                    },
                    position=(lon * 1000.0, lat * 1000.0, 0.0),
                    confidence=max(0.3, 1.0 - vessel.risk_score / 2.0),
                )
            except Exception:
                # Tactical resilience: continue maritime COP generation even if one read fails.
                continue

    def get_maritime_picture(self, region: str = "all") -> MaritimePicture:
        self._feed_positions_to_sensor_manager()
        vessels = [v.to_dict() for v in self.ais_tracker.get_all_vessels()]
        dark_vessels = [v.to_dict() for v in self.ais_tracker.get_dark_vessels()]
        zone_payload = [z.to_dict() for z in self.zone_manager.get_zones()]
        alerts = [a.to_dict() for a in self.active_alerts[-500:]]
        return MaritimePicture(
            timestamp=datetime.now(timezone.utc),
            region=region,
            vessels=vessels,
            sar_detections=dark_vessels,
            border_alerts=alerts,
            zones=zone_payload,
            statistics={
                "total_vessels": len(vessels),
                "dark_vessels": len(dark_vessels),
                "alerts_active": len(alerts),
                "zones_monitored": len(zone_payload),
            },
        )

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "zones_loaded": len(self.zone_manager.get_zones()),
            "active_alerts": len(self.active_alerts),
            "ais_tracker": self.ais_tracker.get_statistics(),
            "sar_detector": self.sar_detector.health_check(),
        }
