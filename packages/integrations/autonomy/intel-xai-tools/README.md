# intel-xai-tools Integration Adapter

Military/tactical context: this wrapper enables sovereign explainability checks for mission AI models before field activation, with deterministic fixture output for airgapped deployments.

## Source Repository

- URL: https://github.com/intel/intel-xai-tools
- License: Apache 2.0

## Adapter Class

- `IntelXaiToolsAdapter` in `adapter.py`
- `integration_id`: `intel-xai-tools`
- `domain`: `autonomy`
- Logger: `s3m.integrations.autonomy.intel-xai-tools`

## Operational Modes

- **Airgapped**: returns `fixtures/sample_response.json` for safe offline validation.
- **Online**: checks for local module presence and returns readiness metadata (no external API calls).

## Primary Entry Point

- `execute(params)` wraps explainability/fairness workflow invocation.
