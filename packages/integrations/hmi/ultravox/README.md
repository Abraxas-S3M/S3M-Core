# Ultravox Integration

## Purpose

This adapter wraps the Ultravox repository for S3M human-machine teaming voice workflows.

Military/tactical context: it supports low-latency multimodal voice coordination so operators can issue and verify mission commands under disconnected or contested conditions.

## Adapter Class

- `UltravoxAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.hmi.ultravox`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
