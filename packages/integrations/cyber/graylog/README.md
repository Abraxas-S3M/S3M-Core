# graylog integration

## Purpose
This adapter wraps Graylog access patterns for cyber defense teams that need
log-derived threat summaries during military operations.

## Airgapped behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- In non-airgapped mode, the adapter validates local Graylog tool presence and
  returns a local-only simulated response.

## Adapter class
- `GraylogAdapter`
- `integration_id`: `graylog`
- `domain`: `cyber`
