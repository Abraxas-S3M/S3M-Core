# opik integration

This wrapper provides a sovereign S3M HMI integration for **opik**.

## Tactical role

Military/tactical context: command teams can rehearse human-machine teaming flows
with deterministic outputs while disconnected from external infrastructure.

## Adapter

- Class: `OpikAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.hmi.opik`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local tool availability (binary/path checks) and returns readiness metadata.
- No external API calls are performed.
