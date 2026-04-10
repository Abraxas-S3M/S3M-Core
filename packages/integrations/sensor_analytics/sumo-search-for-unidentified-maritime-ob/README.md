# SUMO (Search for Unidentified Maritime Objects) Integration

## Purpose

This adapter wraps SUMO-style SAR maritime object detection tooling for S3M
sensor analytics workflows.

Military/tactical context: naval and coast-defense operators use this wrapper
to screen SAR scenes for non-cooperative vessel contacts during disconnected
operations where external services are unavailable.

## Adapter Class

- `SumosearchForUnidentifiedAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace:
  `s3m.integrations.sensor_analytics.sumo-search-for-unidentified-maritime-ob`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture output from
  `fixtures/sample_response.json`.
- **Online mode**: checks only local binary/path readiness and performs no
  external API access.

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
