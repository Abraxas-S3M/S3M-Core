# nocobase/nocobase maintenance integration

This wrapper provides an S3M `IntegrationAdapter` for **nocobase/nocobase** in Procurement & Maintenance workflows.

## Tactical role

The adapter supports sovereign maintenance dashboarding by exposing a stable interface for local KPI and asset status views. Airgapped mode returns deterministic fixture data so operations centers can train and rehearse without external links.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime hints (`nocobase`, `node`, or `NOCOBASE_HOME`).
- `execute()` validates and normalizes payloads, then returns fixture data in airgapped mode.

## Security stance

- No external API calls are executed.
- Input payloads are strictly validated for predictable tactical replay.
