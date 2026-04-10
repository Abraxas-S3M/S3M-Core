# lang-air-ground-teaming Integration

S3M swarm-domain adapter for **lang-air-ground-teaming** (`https://github.com/KumarRobotics/lang-air-ground-teaming`).

## Military / Tactical Context
This adapter supports language-to-mission planning for mixed air and ground
robot teams, helping commanders translate intent into synchronized maneuvers in
unknown or contested environments while remaining fully airgapped.

## Adapter Class
- `LangAirGroundTeamingAdapter`
- `integration_id = "lang-air-ground-teaming"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.lang-air-ground-teaming`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries, modules, and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
