# S3M Phase 5 — Layer 02 Threat Detection and Sensor Fusion Foundation

## Overview

Phase 5 introduces **Layer 02** in the S3M stack: a local, air-gapped threat detection and sensor-fusion pipeline built for NVIDIA Jetson AGX Orin deployment.  
This layer converts raw tactical signals into structured threat events and forwards them to **Layer 01 (LLM Core)** for military assessment.

**Core mission objective:** detect, normalize, prioritize, and route threats from multiple sources without external dependencies.

---

## Architecture Summary

### Layering Context

- **Layer 02 (this phase):** Threat Detection + Sensor Fusion Foundation
- **Layer 01 (existing):** Quad-engine LLM Core (Phi-3, Grok, Mistral, ALLaM)

### Major Components

#### `src/threat_detection/`

- `models.py`  
  Shared threat datamodels:
  - `ThreatEvent`
  - `ThreatLevel`
  - `ThreatSource`
  - `ThreatCategory`
  - `DetectionResult`

- `suricata_adapter.py`  
  Parses Suricata EVE JSON (`event_type: alert`) into `ThreatEvent`.

- `wazuh_adapter.py`  
  Parses Wazuh alerts JSON into `ThreatEvent`.

- `object_detector.py`  
  Wraps local YOLOv8/TensorRT inference. If `ultralytics` is unavailable, enters deterministic stub mode and still emits tactical events.

- `anomaly_detector.py`  
  Uses `IsolationForest` when available, with secure fallback to Z-score anomaly detection.

- `threat_classifier.py`  
  Routes events to Layer 01 orchestrator:
  - CYBER → Grok (reasoning)
  - KINETIC → Phi-3 (tactical)
  - ELECTRONIC_WARFARE → Grok
  - HYBRID → consensus
  - SURVEILLANCE → Mistral (planning)

- `threat_manager.py`  
  Central coordinator for ingest, filtering, stats, per-event LLM assessment, SITREP generation, and JSON export.

#### `src/sensor_fusion/`

- `models.py`
  - `SensorReading`, `Track`, `TrackState`, `SensorType`
- `ekf_filter.py`
  - 3D constant-velocity EKF over `[x, y, z, vx, vy, vz]`
  - NumPy fallback path available
- `track_fuser.py`
  - Nearest-neighbor association
  - Track lifecycle transitions: tentative → confirmed → lost → deleted
- `sensor_manager.py`
  - Sensor registration
  - Reading ingestion and batching
  - Fused track conversion into Layer 02 `ThreatEvent` records

---

## Data Flow

1. **Sensors and Security Feeds**
   - Suricata, Wazuh, EO/RF sensors, telemetry streams.
2. **Layer 02 Processing**
   - Adapters parse and validate data.
   - Sensor readings are fused into tracks.
   - Object/anomaly detections become standardized `ThreatEvent`.
3. **Threat Prioritization**
   - Event severity/category routing metadata assigned.
4. **LLM Core Integration (Layer 01)**
   - `ThreatClassifier` builds tactical prompt and calls orchestrator.
5. **Operational Outputs**
   - Event log, stats, SITREP, assessed threat records via API.

---

## API Endpoints (Phase 5)

### Threat Detection

- `POST /threats/ingest/suricata`
- `POST /threats/ingest/wazuh`
- `POST /threats/ingest/image`
- `POST /threats/ingest/telemetry`
- `POST /threats/ingest/manual`
- `GET /threats`
- `GET /threats/stats`
- `GET /threats/{event_id}`
- `POST /threats/{event_id}/assess`
- `GET /threats/sitrep`

### Sensor Fusion

- `GET /sensors`
- `GET /sensors/tracks`
- `POST /sensors/register`
- `POST /sensors/ingest`

All request/response schemas are in `src/api/threat_models.py`.

---

## Configuration

### `configs/threat_detection.yaml`

Controls:
- Suricata and Wazuh ingestion paths
- Poll intervals
- YOLO model path and confidence threshold
- Anomaly detector contamination/estimators
- Threat log capacity
- Sensor fusion association and EKF parameters

### `configs/threat_routing.yaml`

Defines:
- Threat category → LLM engine mapping
- Prompt templates for each threat category

---

## Integration with Existing Phase 4 API

`src/api/server.py` now includes:

- `threat_router`
- `sensor_router`

No existing Phase 1–4 endpoints were altered.

---

## Testing

New tests:

- `tests/test_threat_models.py`
- `tests/test_suricata_adapter.py`
- `tests/test_wazuh_adapter.py`
- `tests/test_object_detector.py`
- `tests/test_anomaly_detector.py`
- `tests/test_threat_classifier.py`
- `tests/test_threat_manager.py`
- `tests/test_sensor_fusion.py`
- `tests/test_threat_api.py`

Run:

```bash
python -m pytest tests/test_threat_*.py tests/test_sensor_fusion.py -v
```

---

## Operational Demos

- Threat pipeline demo:
  ```bash
  python scripts/run_threat_detection.py
  ```

- Sensor fusion demo:
  ```bash
  python scripts/demo_sensor_fusion.py
  ```

---

## Security and Deployment Notes

- Air-gapped operation only; no external API calls.
- Input validation is enforced across adapters, managers, and API schemas.
- Event normalization reduces parser ambiguity and supports downstream auditability.
- Tactical comments and prompt structures preserve military-response context.

---

## Future Work (Phase 6+ Foundation)

Potential follow-on capabilities now enabled by this foundation:

1. Multi-hypothesis track management and advanced gating.
2. UKF/JIPDA track confidence fusion.
3. RF spectrum classifier integration for EW signatures.
4. Cross-layer mission planning feedback loops.
5. Persistent encrypted event store and replay tooling.
6. Autonomous countermeasure recommendation validation with rules-of-engagement guardrails.
