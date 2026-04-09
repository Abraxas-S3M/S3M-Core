# XAI-Cybersecurity Integration Adapter

Military/tactical context: this wrapper supports explainable cyber defense decisions so SOC operators can justify rapid containment actions in contested environments.

## Source Repository

- URL: https://github.com/ivoafonsobispo/XAI-Cybersecurity
- License: MIT

## Adapter Class

- `XaiCybersecurityAdapter` in `adapter.py`
- `integration_id`: `xai-cybersecurity`
- `domain`: `autonomy`
- Logger: `s3m.integrations.autonomy.xai-cybersecurity`

## Operational Modes

- **Airgapped**: returns deterministic detection explanation from `fixtures/sample_response.json`.
- **Online**: validates local package availability and exposes readiness metadata.

## Primary Entry Point

- `execute(params)` wraps explainable intrusion-alert analysis.
