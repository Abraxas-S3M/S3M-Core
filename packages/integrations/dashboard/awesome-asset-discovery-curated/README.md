# Awesome-Asset-Discovery (Curated) integration

This wrapper provides a sovereign S3M dashboard integration for **Awesome-Asset-Discovery (Curated)**.

## Tactical role

The adapter supports mission dashboards by exposing a consistent execution and health-check surface. In contested or disconnected environments, it returns vetted fixture data so operators can continue planning without external connectivity.

## Files

- `adapter.py`: IntegrationAdapter implementation
- `manifest.yaml`: catalog metadata
- `fixtures/sample_response.json`: airgapped response payload

## Runtime behavior

- Airgapped mode (`mode="airgapped"` or `S3M_AIRGAPPED=true`) always serves fixture data.
- Online mode remains local-only and validates runtime availability via `git or python3`.
- No external API calls are executed.
