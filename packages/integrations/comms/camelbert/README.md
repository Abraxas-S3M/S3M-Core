# CAMeLBERT Integration

S3M communications-domain wrapper for **CAMeLBERT**.

## Military / Tactical Context
This adapter helps communications intelligence teams classify Arabic message
intent to prioritize urgent command-and-control traffic during denied-connectivity
operations.

## Adapter Class
- `CamelbertAdapter`
- `integration_id = "camelbert"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.camelbert`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local NLP runtime dependencies.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
