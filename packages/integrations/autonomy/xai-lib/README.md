# XAI-Lib Integration Adapter

Military/tactical context: this wrapper lets operators benchmark multiple explanation methods and select the most defensible rationale for autonomous mission decisions.

## Source Repository

- URL: https://github.com/kdd-lab/XAI-Lib
- License: MIT

## Adapter Class

- `XaiLibAdapter` in `adapter.py`
- `integration_id`: `xai-lib`
- `domain`: `autonomy`
- Logger: `s3m.integrations.autonomy.xai-lib`

## Operational Modes

- **Airgapped**: uses `fixtures/sample_response.json` for deterministic offline execution.
- **Online**: validates local package availability and returns readiness metadata.

## Primary Entry Point

- `execute(params)` wraps explainer-comparison style operations.
