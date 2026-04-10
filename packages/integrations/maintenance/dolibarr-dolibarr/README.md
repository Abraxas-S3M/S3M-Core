# dolibarr/dolibarr maintenance integration

This wrapper provides an S3M `IntegrationAdapter` for **dolibarr/dolibarr** in Procurement & Maintenance operations.

## Tactical role

The adapter gives logistics and maintenance cells a consistent local interface to procurement and sustainment telemetry. In airgapped environments, it returns deterministic fixture data so command-post workflows can continue without internet access.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local runtime hints (`php`, `dolibarr`, or `DOLIBARR_HOME`).
- `execute()` validates request payloads and returns fixture output in airgapped mode.

## Security stance

- No external API calls are made.
- Inputs are validated and normalized to JSON-safe structures before processing.
