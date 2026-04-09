# kr_autonomous_flight Integration

S3M adapter for [kr_autonomous_flight](https://github.com/KumarRobotics/kr_autonomous_flight) in the `navigation` domain.

## Tactical purpose

This wrapper standardizes readiness checks for research-grade autonomous flight in GPS-denied operations.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local binary/package availability for ROS-based deployment
- Returns deterministic fixture payloads for airgapped mission rehearsal

## Airgapped behavior

When running in airgapped mode, `execute()` returns `fixtures/sample_response.json` without invoking external services.
