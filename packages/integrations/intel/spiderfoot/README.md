# SpiderFoot Integration

S3M intel-domain wrapper for **spiderfoot**.

## Military / Tactical Context
This adapter supports reconnaissance and threat-intelligence triage for mission
staff while preserving deterministic behavior during disconnected operations.

## Adapter Class
- `SpiderfootAdapter`
- `integration_id = "spiderfoot"`
- `domain = "intel"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
