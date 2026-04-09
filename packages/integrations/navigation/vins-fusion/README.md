# VINS-Fusion Integration

S3M adapter for [VINS-Fusion](https://github.com/HKUST-Aerial-Robotics/VINS-Fusion) in the `navigation` domain.

## Tactical purpose

This wrapper provides a controlled interface for visual-inertial and GPS fusion readiness checks on sovereign mission infrastructure.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime availability using ROS package/binary probes
- Supports deterministic fixture responses in airgapped mode

## Airgapped behavior

With airgapped mode enabled, `execute()` returns `fixtures/sample_response.json` to emulate estimator output without external dependencies.
