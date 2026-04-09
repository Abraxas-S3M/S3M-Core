# taranis-ai Integration

S3M adapter wrapper for [taranis-ai](https://github.com/taranis-ai/taranis-ai) in the intelligence domain.

## Tactical purpose

This integration supports OSINT collection and AI-assisted situational analysis for command briefing workflows running on sovereign infrastructure.

## Capabilities

- Loads metadata from `manifest.yaml` for registry discovery.
- Validates local runtime/tooling presence before online-mode readiness.
- Returns deterministic fixture output in `airgapped` mode.

## Airgapped behavior

When `mode="airgapped"`, `execute()` returns `fixtures/sample_response.json` and does not make external requests.
