# FYP-Maritime_Surveillance Integration

## Purpose

This adapter wraps
[FYP-Maritime_Surveillance](https://github.com/sakunaharinda/FYP-Maritime_Surveillance)
for S3M sensor analytics deployments.

Military/tactical context: thermal-based vessel detection and tracking supports
night operations, perimeter enforcement, and rapid cueing of patrol assets in
coastal defense missions.

## Adapter Class

- `FypMaritimeSurveillanceAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.fyp-maritime-surveillance`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from
  `fixtures/sample_response.json`.
- **Online mode**: performs local dependency checks only and does not call
  external APIs.

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by
`get_manifest()`.
