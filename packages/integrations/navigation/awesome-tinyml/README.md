# awesome-tinyml Integration

S3M navigation-domain adapter for **awesome-tinyml** (`https://github.com/umitkacar/awesome-tinyml`).

## Military / Tactical Context
This adapter assists operators in selecting quantized, edge-capable inference stacks for offline navigation workloads on sovereign compute nodes.

## Adapter Class
- `AwesomeTinymlAdapter`
- `integration_id = "awesome-tinyml"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.awesome-tinyml`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local edge runtime toolchain hints.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
