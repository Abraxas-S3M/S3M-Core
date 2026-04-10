# Arabic-Resources Integration

S3M communications-domain wrapper for **Arabic-Resources**.

## Military / Tactical Context
This adapter provides offline access to Arabic NLP resource catalogs so comms
analytics teams can select trustworthy local datasets and models in airgapped
mission environments.

## Adapter Class
- `ArabicResourcesAdapter`
- `integration_id = "arabic-resources"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.arabic-resources`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks configured local resource index paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
