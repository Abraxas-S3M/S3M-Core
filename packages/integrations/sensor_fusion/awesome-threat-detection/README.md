# awesome-threat-detection Integration

## Purpose

This adapter wraps the `awesome-threat-detection` repository as a curated
threat-detection knowledge source for S3M sensor-fusion planning workflows.

Military/tactical context: this wrapper provides deterministic threat-hunting
reference outputs to support mission rehearsal and sensor-emitter triage in
airgapped command environments.

## Adapter Class

- `AwesomeThreatDetectionAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.awesome-threat-detection`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from
  `fixtures/sample_response.json`
- **Online mode**: checks local command/path availability for Suricata/Zeek
  style toolchains used in threat-detection workflows

## Manifest

Integration metadata is stored in `manifest.yaml` and returned by
`get_manifest()`.
