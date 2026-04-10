# arabic-text-classification-summarization Integration

S3M communications-domain wrapper for **arabic-text-classification-summarization**.

## Military / Tactical Context
This adapter classifies and summarizes Arabic mission traffic to help command
staff quickly identify operationally relevant communication threads.

## Adapter Class
- `ArabicTextClassificationSummarizationAdapter`
- `integration_id = "arabic-text-classification-summarization"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.arabic-text-classification-summarization`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` verifies local transformer runtime dependencies.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
