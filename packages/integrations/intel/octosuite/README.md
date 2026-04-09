# Octosuite Integration

S3M intel-domain wrapper for **octosuite**.

## Military / Tactical Context
This adapter supports repository-centric OSINT investigations used for
counterintelligence, provenance review, and supply-chain risk assessment in
sovereign operational environments.

## Adapter Class
- `OctosuiteAdapter`
- `integration_id = "octosuite"`
- `domain = "intel"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
