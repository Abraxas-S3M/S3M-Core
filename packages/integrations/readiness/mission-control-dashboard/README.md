# mission-control-dashboard Integration

S3M wrapper for PatternFly mission-control dashboard examples on GitHub.

## Military/Tactical Context

This adapter standardizes defense-grade command-surface metrics for personnel
readiness monitoring, helping commanders maintain staffing and training posture
in sovereign airgapped deployments.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks configured local path or runtime hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
- Online mode keeps all behavior local and policy-compliant.

## Adapter Class

- Module: `packages.integrations.readiness.mission-control-dashboard.adapter`
- Class: `MissionControlDashboardAdapter`
- Integration ID: `mission-control-dashboard`
- Domain: `readiness`
