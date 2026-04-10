# orangehrm/orangehrm maintenance integration

This wrapper provides an S3M `IntegrationAdapter` for **orangehrm/orangehrm** in Procurement & Maintenance workflows.

## Tactical role

The adapter helps maintenance commands track workforce readiness, certification posture, and crew assignment pressure while operating in sovereign offline environments.

## Behavior

- `get_manifest()` reads integration metadata from `manifest.yaml`.
- `validate_availability()` checks for local runtime hints (`php`, `orangehrm`, or `ORANGEHRM_HOME`).
- `execute()` validates payloads and returns deterministic fixture data in airgapped mode.

## Security stance

- No external API calls are performed.
- Input data is validated and normalized before use.
