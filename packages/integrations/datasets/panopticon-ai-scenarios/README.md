# Panopticon AI Scenarios Integration

S3M dataset-domain wrapper for **Panopticon AI Scenarios**.

## Military / Tactical Context
This adapter supports doctrine testing and AI agent rehearsal by standardizing
access to wargaming scenario datasets in sovereign, offline simulation stacks.

## Adapter Class
- `PanopticonAiScenariosAdapter`
- `integration_id = "panopticon-ai-scenarios"`
- `domain = "datasets"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local scenario mirrors and simulation tooling.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
