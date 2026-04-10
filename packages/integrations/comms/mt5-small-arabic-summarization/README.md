# mt5-small-Arabic-Summarization Integration

S3M communications-domain wrapper for **mt5-small-Arabic-Summarization**.

## Military / Tactical Context
This adapter compresses Arabic communication traffic into concise summaries so
mission cells can rapidly triage high-volume reporting during disconnected and
contested operations.

## Adapter Class
- `Mt5SmallArabicSummarizationAdapter`
- `integration_id = "mt5-small-arabic-summarization"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.mt5-small-arabic-summarization`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local model/runtime dependencies only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
