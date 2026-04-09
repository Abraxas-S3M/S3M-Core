# TaiWan-Situation Integration

S3M wrapper for the
[TaiWan-situation](https://github.com/Pluto114/TaiWan-situation) repository.

## Military/Tactical Context

This adapter standardizes geopolitical tension index outputs so command teams
can monitor escalation signals and update watch conditions during mission
planning in airgapped deployments.

## Behavior

- **Airgapped mode**: returns `fixtures/sample_response.json`.
- **Online mode**: validates local dashboard dependencies and returns a
  structured handoff payload for orchestrator-managed execution.

## Files

- `adapter.py`: `TaiwanSituationAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: offline fixture payload

