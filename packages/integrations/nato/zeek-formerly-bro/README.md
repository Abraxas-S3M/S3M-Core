# Zeek (formerly Bro) Integration

S3M NATO-domain wrapper for **Zeek (formerly Bro)**.

## Military / Tactical Context
This adapter enables protocol-level network telemetry rehearsal for coalition
cyber exercises where deterministic forensic outputs are required in disconnected
mission environments.

## Adapter Class
- `ZeekformerlyBroAdapter`
- `integration_id = "zeek-formerly-bro"`
- `domain = "nato"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local Zeek/Bro runtime availability only.
- `execute()` returns deterministic fixture results in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
