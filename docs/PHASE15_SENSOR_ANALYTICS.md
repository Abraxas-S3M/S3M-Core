# S3M Phase 15 — Layer 09 Sensor & Remote Sensing Analytics

Phase 15 introduces **Layer 09** to bridge wide-area remote sensing with tactical fusion from Phase 5.
The layer focuses on Saudi maritime/border awareness across the Red Sea, Persian Gulf, Bab el-Mandeb,
Strait of Hormuz approaches, and Gulf of Aden.

## 1) Architecture Overview

Layer 09 modules:

- `services/sensor_analytics/sar/`: SAR preprocessing, ship detection backends, vessel classifier
- `services/sensor_analytics/ais/`: AIS file ingestion (CSV/NMEA), tracking, anomaly detection
- `services/sensor_analytics/border/`: Zone manager and border surveillance engine
- `services/sensor_analytics/geospatial/`: Geospatial math and GeoJSON utilities
- `services/sensor_analytics/fusion_engine.py`: SAR + AIS + zones fusion into maritime picture
- `services/sensor_analytics/manager.py`: Top-level orchestration API for Layer 09
- `src/api/sensor_analytics_routes.py`: FastAPI routes (16 endpoints)

Operational dataflow:

1. Satellite SAR imagery is preprocessed, tiled, and detected for ship-like contacts.
2. AIS transponder files are ingested and used to maintain vessel tracks and risk scores.
3. SAR detections are matched to AIS; unmatched detections are treated as dark-vessel candidates.
4. Zone scans and AIS anomalies generate border alerts.
5. Alerts are mapped into Phase 5 `ThreatEvent` objects (via `ThreatManager` integration).
6. Vessel position updates are fed to Phase 5 `SensorManager` as radar-like remote sensor readings.
7. A unified `MaritimePicture` is produced for COP overlay integration in dashboard workflows.

## 2) SAR Detection Pipeline

Pipeline stages:

1. **Preprocess** (`SARPreprocessor`)
   - image load via PIL/tifffile with graceful fallback
   - despeckle using Lee or median filter
   - normalize to uint8 [0, 255]
   - tile large images for detector batch processing
2. **Detect** (`SARDetector`)
   - backend preference:
     - local YOLOv8 model path
     - ultralytics runtime
     - ONNX runtime
     - Phase 5 object detector fallback
     - stub threshold detector
3. **Postprocess**
   - NMS de-duplication
   - pixel-to-geo interpolation
   - vessel dimensions estimated from bbox + pixel resolution
4. **Classify** (`SARShipClassifier`)
   - rule-based class assignment by vessel length and L/W ratio
   - optional local LLM availability flag for future refinement

If no model is available, detections still flow with `model_not_loaded=true`.

## 3) AIS Tracking

`AISTracker` features:

- file-based ingestion (air-gapped mode)
- NMEA payload decode and CSV parsing
- vessel registry keyed by MMSI
- track history retention (100 points)
- dark vessel detection when AIS goes stale
- SAR-to-AIS nearest match within configurable radius

## 4) AIS Anomalies and Military Relevance

`AISAnomalyDetector` currently detects:

1. `ais_gap` — vessel transmitted then silent (>1 hour)
2. `speed_anomaly` — abrupt speed change (>50%)
3. `course_deviation` — heading shift >90 deg
4. `zone_intrusion` — vessel enters restricted zone
5. `position_spoofing` — implausible >100 km jump
6. `loitering` — prolonged low-speed behavior

Military/tactical significance:

- AIS gaps near chokepoints can indicate evasive intent.
- spoofing and abrupt maneuvers often correlate with deceptive tracks.
- loitering around sensitive maritime infrastructure can precede hostile or illicit activity.

## 5) Border Surveillance

`ZoneManager`:

- loads zones from `configs/sensor-analytics/zones.yaml`
- point-in-polygon checks by ray-casting
- supports zone lookup and threat-level updates

`BorderSurveillanceEngine`:

- scans each zone for AIS vessels and anomalies
- identifies dark-vessel risk (AIS drop or unmatched SAR)
- generates `BorderAlert` objects
- maps alerts to Phase 5 threat events with severity/category mapping

## 6) Maritime Fusion

`MaritimeFusionEngine` responsibilities:

- ingest AIS files and update vessel states
- match SAR contacts to AIS vessels
- classify unmatched SAR contacts as dark-vessel candidates
- produce `MaritimePicture` with vessels, detections, alerts, zones, and statistics
- export picture to GeoJSON for COP usage

Outputs include:

- total tracked vessels
- dark vessel count
- active alerts
- per-classification statistics

## 7) Geospatial Utilities

`GeospatialProcessor` provides:

- Haversine distance (km)
- point-in-polygon checks
- bearing computation
- geo/local coordinate conversion
- GeoJSON create/export/load

`SatelliteImageProcessor` provides:

- Sentinel-1 and Sentinel-2 loading with fallbacks
- simple CFAR-like ship mask extraction
- detection chip extraction
- image coverage area estimate

## 8) Saudi Maritime Zones

Configured default zones cover:

- Red Sea Northern Sector
- Red Sea Southern Sector (Bab el-Mandeb)
- Persian Gulf Eastern Sector
- Strait of Hormuz Approach
- Jubail Industrial Coast
- Gulf of Aden Approach

## 9) Integration with Existing Layers

### Phase 5 Threat Detection

- Border alerts are converted to `ThreatEvent` objects
- mapping examples:
  - dark vessel -> `KINETIC/HIGH`
  - zone intrusion -> `SURVEILLANCE/MEDIUM`
  - anomalous track -> `SURVEILLANCE/LOW`

### Phase 5 Sensor Fusion

- vessel positions are pushed into `SensorManager` as remote radar-like reads
- this enables downstream fused track workflows without modifying existing layer code

### Phase 6 Dashboard

- `MaritimePicture` can be exported as GeoJSON for COP overlays and mission UI integration

## 10) API Endpoint Reference (16 endpoints)

1. `POST /sensor-analytics/sar/detect`
2. `GET /sensor-analytics/sar/model`
3. `POST /sensor-analytics/ais/ingest`
4. `GET /sensor-analytics/ais/vessels`
5. `GET /sensor-analytics/ais/vessels/{mmsi}`
6. `GET /sensor-analytics/ais/dark`
7. `POST /sensor-analytics/border/scan`
8. `GET /sensor-analytics/border/zones`
9. `POST /sensor-analytics/border/zones`
10. `GET /sensor-analytics/border/alerts`
11. `GET /sensor-analytics/maritime/picture`
12. `GET /sensor-analytics/maritime/stats`
13. `POST /sensor-analytics/maritime/export`
14. `GET /sensor-analytics/status`
15. `GET /sensor-analytics/datasets`
16. `GET /sensor-analytics/border/status`

## 11) Configuration Reference

Main config: `configs/sensor-analytics.yaml`

- SAR backend preferences and thresholds
- AIS ingestion limits and risk scoring weights
- anomaly thresholds for operational alerts
- border zone config path and scan intervals
- geospatial origin defaults
- maritime fusion integration toggles
- dataset registry location

## 12) Future Direction (Phase 16)

Planned interoperability expansion:

- standardized STANAG-like message export
- coalition track-sharing adapters
- schema mapping for defense geospatial exchange formats

