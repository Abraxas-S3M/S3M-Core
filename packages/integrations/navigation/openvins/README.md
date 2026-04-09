# OpenVINS Integration

S3M adapter for [OpenVINS](https://github.com/rpng/open_vins) in the `navigation` domain.

## Tactical purpose

This wrapper enables consistent visual-inertial state-estimation readiness checks for disconnected tactical navigation systems.

## Capabilities

- Loads canonical metadata from `manifest.yaml`
- Validates local ROS/command availability without network access
- Returns deterministic fixture data for airgapped mission rehearsal

## Airgapped behavior

When airgapped mode is active, `execute()` returns `fixtures/sample_response.json` as the emulated state-estimator output.
