# trustyai-explainability Integration

S3M adapter for the TrustyAI explainability toolkit.

## Tactical purpose

This integration supports explainability and fairness evidence generation for
mission AI decisions in airgapped or communications-denied settings.

## Files

- `adapter.py` - `TrustyaiExplainabilityAdapter` implementation.
- `manifest.yaml` - metadata for discovery and governance.
- `fixtures/sample_response.json` - deterministic airgapped audit payload.

## Airgapped behavior

In airgapped mode, `execute()` returns fixture data to keep testing and mission
rehearsal outputs deterministic.

## Online behavior

`validate_availability()` verifies local `java` plus either a `trustyai` binary
or a `TRUSTYAI_JAR` path.
