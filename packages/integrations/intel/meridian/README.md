# meridian Integration

S3M adapter wrapper for [meridian](https://github.com/iliane5/meridian) in the intelligence domain.

## Tactical purpose

This wrapper supports AI-assisted news ingestion and prioritization to produce daily operational briefs for military planners in sovereign environments.

## Capabilities

- Loads registry metadata from `manifest.yaml`.
- Performs local availability checks for runtime readiness.
- Provides deterministic fixture output for airgapped execution.

## Airgapped behavior

When `mode="airgapped"`, the adapter returns `fixtures/sample_response.json` for repeatable briefing rehearsal and CI verification.
