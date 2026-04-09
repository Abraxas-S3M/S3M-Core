# Awesome-Asset-Discovery Integration

S3M military-domain wrapper for **Awesome-Asset-Discovery**.

## Military / Tactical Context
This adapter supports asset discovery and exposure prioritization so operators
can harden mission infrastructure before adversary reconnaissance campaigns.

## Adapter Class
- `AwesomeAssetDiscoveryAdapter`
- `integration_id = "awesome-asset-discovery"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local discovery tools and configured paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
