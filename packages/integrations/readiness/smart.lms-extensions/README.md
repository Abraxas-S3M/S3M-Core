# Smart.LMS extensions Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Smart.LMS extension workflows
that track personnel training completion and certification status.

## Military/Tactical Context
Command elements require reliable readiness snapshots to confirm that mission
roles are filled by currently certified operators before deployment windows.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Validation
`validate_availability()` checks configured local binaries, local paths, and
known module/CLI candidates for Smart.LMS or learnhouse deployments.
