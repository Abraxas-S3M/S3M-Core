# opensearch-project integration

## Purpose
This adapter provides a sovereign-safe wrapper around OpenSearch analytics
workflows for mission cyber intelligence and threat hunting.

## Airgapped behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- In non-airgapped mode, the adapter only performs local tool checks and
  returns a controlled simulated result.

## Adapter class
- `OpensearchProjectAdapter`
- `integration_id`: `opensearch-project`
- `domain`: `cyber`
