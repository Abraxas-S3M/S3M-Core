# MAVROS Integration

## Purpose

This adapter wraps the MAVROS repository for S3M autonomous UAV command-and-telemetry bridge workflows.

Military/tactical context: it supports deterministic verification of MAVLink-to-ROS bridging so mission controllers can validate command relay and telemetry integrity inside sovereign infrastructure.

## Adapter Class

- `MavrosAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.mavros`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
