# LLM-controlled-drone Integration

## Purpose

This adapter wraps the LLM-controlled-drone repository for S3M natural-language drone tasking workflows.

Military/tactical context: it enables operators to issue concise mission-language commands to autonomous drones that fuse local LLM reasoning and onboard vision for reconnaissance and target detection.

## Adapter Class

- `LlmControlledDroneAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.hmi.llm-controlled-drone`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
