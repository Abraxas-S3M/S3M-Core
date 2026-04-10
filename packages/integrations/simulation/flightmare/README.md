# flightmare Integration

## Purpose

This adapter wraps the `flightmare` UAV simulation repository for S3M simulation mission rehearsal workflows.

Military/tactical context: Flightmare allows high-rate drone mission training loops where command AI can evaluate aggressive maneuver policy behavior in contested environments while operating fully offline.

## Adapter Class

- `FlightmareAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.simulation.flightmare`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local runtime presence (binary/path/module) without external API calls

## Manifest

Metadata is loaded from `manifest.yaml` by `get_manifest()`.
