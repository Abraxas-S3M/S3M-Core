# Groot Integration Adapter

Military/tactical context: this wrapper supports behavior-tree authoring and diagnostics so autonomy logic can be validated before deployment to mission platforms.

## Source Repository

- URL: https://github.com/BehaviorTree/Groot
- License: MIT

## Adapter Class

- `GrootAdapter` in `adapter.py`
- `integration_id`: `groot`
- `domain`: `autonomy`
- Logger: `s3m.integrations.autonomy.groot`

## Operational Modes

- **Airgapped**: returns deterministic behavior-tree validation output from fixture.
- **Online**: checks for local Groot executable availability and reports readiness.

## Primary Entry Point

- `execute(params)` wraps behavior-tree validation and diagnostics requests.
