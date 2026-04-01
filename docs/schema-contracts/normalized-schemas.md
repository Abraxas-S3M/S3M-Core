# Normalized Schema Contracts

This document defines required contracts for all normalized provider outputs.

## Common Base

All normalized records inherit from `BaseNormalizedRecord` and include:

- `record_id`
- `provenance`
- `timestamp`
- `geo_point` (optional)
- `tags`
- `raw_data_ref` (optional)
- `created_at`

## Domain Contracts

- Geospatial: `NormalizedGeoObservation`
- Threat Intel: `NormalizedThreatIndicator`
- Event Intel: `NormalizedGlobalEvent`
- Maritime: `NormalizedVesselTrack`
- Flight: `NormalizedFlightTrack`
- Weather: `NormalizedWeatherObservation`
- Terrain: `NormalizedMapLayer`
- Identity: `ProviderAccount`, `CredentialRef`, `ConnectorHealthStatus`

## Validation Expectations

- Numeric ranges enforced where specified.
- Provider provenance must include source identifier and classification.
- Fields should be deterministic and serializable to JSON.
