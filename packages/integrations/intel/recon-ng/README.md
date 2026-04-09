# Recon-ng Integration

S3M intel-domain wrapper for **recon-ng**.

## Military / Tactical Context
This adapter allows intelligence teams to run repeatable reconnaissance against
areas of operational interest while preserving deterministic behavior in
airgapped deployments.

## Adapter Class
- `ReconNgAdapter`
- `integration_id = "recon-ng"`
- `domain = "intel"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
