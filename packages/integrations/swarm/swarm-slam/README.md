# Swarm-SLAM Integration

S3M swarm-domain adapter for **Swarm-SLAM** (`https://github.com/MISTLab/Swarm-SLAM`).

## Military / Tactical Context
This adapter supports decentralized collaborative mapping for multi-robot teams
conducting reconnaissance and area-clearance missions in contested terrain where
GPS and continuous backhaul links may be denied.

## Adapter Class
- `SwarmSlamAdapter`
- `integration_id = "swarm-slam"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.swarm-slam`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries, modules, and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
