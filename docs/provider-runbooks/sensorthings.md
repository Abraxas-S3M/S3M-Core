# OGC SensorThings Provider Runbook (Simulation Interop)

## Standard Overview
- OGC SensorThings API is an open interoperability standard for IoT-like sensor data.
- In S3M Chunk 10, this adapter is used for **simulation and test harness ingest only**.
- It bridges distributed sensor feeds into S3M fusion contracts without relying on DIS/HLA-native payloads.

## S3M SensorThings Endpoint
- Default endpoint: `http://localhost:8080/FROST-Server/v1.1`
- Environment override:
  - `S3M_SENSORTHINGS_URL`

## Core SensorThings Entities
- `Things`
- `Sensors`
- `Datastreams`
- `Observations`
- `ObservedProperties`
- `Locations`
- `FeaturesOfInterest`

## S3M Sensor Types
The adapter defines seven tactical simulation sensor archetypes:
- `ground_radar`
- `weather_station`
- `seismic_sensor`
- `chemical_detector`
- `radiation_monitor`
- `acoustic_sensor`
- `ais_receiver`

Each sensor type maps to one or more datastream properties (for example radar range/bearing/RCS/velocity).

## S3M Integration Bridge
- Adapter call: `feed_to_sensor_fusion(observations)`
- Bridge behavior:
  - Normalizes SensorThings observations into SensorReading-compatible dictionaries.
  - Preserves timestamp, value, position, unit, and quality.
  - Allows Phase 5 fusion components to process non-DIS/HLA sources in joint simulation tests.

## Stub / Air-Gapped Behavior
- If FROST-Server is unavailable (or in air-gapped mode), adapter falls back to fixture-backed stub mode.
- Stub mode still supports:
  - listing things,
  - polling observations,
  - registering S3M sensors,
  - publishing synthetic observations,
  - feeding normalized payloads to sensor fusion.

## Smoke Test
```bash
python3 -m pytest packages/providers/sim-sensorthings/tests/test_sensorthings_adapter.py -v
```

