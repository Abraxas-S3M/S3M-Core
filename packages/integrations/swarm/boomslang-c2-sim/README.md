
# boomslang-c2-sim Integration

## Purpose

This adapter wraps **boomslang-c2-sim** for S3M swarm-domain mission workflows.

Military/tactical context: it enables sovereign operators to validate swarm
command behavior and simulation readiness in disconnected and contested
environments where external network calls are disallowed.

## Adapter Class

- `BoomslangC2SimAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.boomslang-c2-sim`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture payload from
  `fixtures/sample_response.json`
- **Online mode**: performs local toolchain availability checks and returns
  orchestrator-governed runtime status

## Manifest

Metadata is declared in `manifest.yaml` and returned by `get_manifest()`.
