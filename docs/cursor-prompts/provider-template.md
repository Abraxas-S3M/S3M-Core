# Cursor Prompt Template - New S3M Provider Adapter

Use this template to add a new provider under `packages/providers/<provider-id>/`.

## Prompt

Build a new S3M provider adapter using `packages/providers/_mock_provider` as the baseline.

Requirements:

1. Create adapter, config, normalizer, fixtures, and tests.
2. Implement `ProviderAdapter` lifecycle methods.
3. Support dual-mode operation:
   - online mode: API fetch
   - airgapped mode: local cache read only
4. Use `SecretProvider` for credentials (no hardcoded secrets).
5. Map payloads into normalized schema dataclasses.
6. Add registry compatibility and health check behavior.
7. Add runbook docs with env vars, endpoints, limits, and smoke tests.

Deliverables:

- Provider package files
- Fixture-based tests passing with pytest
- Documentation updates
