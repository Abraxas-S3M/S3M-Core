"""
S3M Layer 09 — Sensor & Remote Sensing Analytics
Wide-area surveillance: satellite SAR, AIS maritime tracking, border monitoring,
and geospatial AI for Saudi maritime domain awareness.

Subsystems:
- SAR Detection: Ship detection from Sentinel-1/Gaofen-3 SAR satellite imagery
- Maritime Tracking: AIS transponder data fusion with satellite detections
- Border Surveillance: AI-powered anomaly detection for border/coastal zones
- Geospatial AI: Segment Anything for satellite imagery, foundation model adapters
- Data Fusion: Merge SAR + optical + AIS + local sensors into unified maritime picture
- Dataset Manager: SAR ship datasets, satellite imagery catalogs

Integration:
  Satellite imagery → SAR detector → detections → Phase 5 SensorManager → TrackFuser
  AIS data → AIS tracker → vessel tracks → Phase 5 TrackFuser
  Border cameras → anomaly detector → Phase 5 ThreatManager
  Combined maritime picture → Dashboard (Layer 06) COP overlay
"""

from services.sensor_analytics.ais import AISAnomalyDetector, AISParser, AISTracker
from services.sensor_analytics.border import BorderSurveillanceEngine, ZoneManager
from services.sensor_analytics.dataset_manager import RemoteSensingDatasetManager
from services.sensor_analytics.fusion_engine import MaritimeFusionEngine
from services.sensor_analytics.geospatial import GeospatialProcessor
from services.sensor_analytics.manager import SensorAnalyticsManager
from services.sensor_analytics.models import (
    AISMessage,
    AISVessel,
    BorderAlert,
    BorderZone,
    MaritimePicture,
    SARDetection,
    SARImageMeta,
    VesselClassification,
    VesselTrack,
)
from services.sensor_analytics.sar import SARDetector, SARPreprocessor, SARShipClassifier
from services.sensor_analytics.satellite_image_processor import SatelliteImageProcessor

__all__ = [
    "SensorAnalyticsManager",
    "SARDetector",
    "SARDetection",
    "SARImageMeta",
    "AISTracker",
    "AISVessel",
    "AISMessage",
    "VesselTrack",
    "BorderSurveillanceEngine",
    "BorderAlert",
    "BorderZone",
    "GeospatialProcessor",
    "MaritimeFusionEngine",
    "MaritimePicture",
    "VesselClassification",
    "RemoteSensingDatasetManager",
    "SARPreprocessor",
    "SARShipClassifier",
    "AISParser",
    "AISAnomalyDetector",
    "ZoneManager",
    "SatelliteImageProcessor",
]
