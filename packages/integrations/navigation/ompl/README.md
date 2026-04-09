# OMPL Integration

S3M navigation-domain adapter for **OMPL** (`https://github.com/ompl/ompl`).

## Military / Tactical Context
This wrapper supports deterministic motion-planning rehearsals for autonomous
platforms that must operate in disconnected or contested environments.

## Adapter Class
- `OmplAdapter`
- `integration_id = "ompl"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.ompl`

## Behavior
- `get_manifest()` loads repository metadata from `manifest.yaml`.
- `validate_availability()` checks local module, binary, and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
