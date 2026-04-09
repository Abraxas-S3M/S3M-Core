# Open Transport Data Integration

S3M dataset-domain wrapper for **Open Transport Data**.

## Military / Tactical Context
This adapter supports logistics and sustainment simulation by exposing transport
route/network datasets through a uniform interface suitable for sovereign,
airgapped planning environments.

## Adapter Class
- `OpenTransportDataAdapter`
- `integration_id = "open-transport-data"`
- `domain = "datasets"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local dataset mirrors and graph tooling.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
