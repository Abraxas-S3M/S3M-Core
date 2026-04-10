# horilla integration

This wrapper provides a sovereign S3M readiness integration for **horilla**.

## Tactical role

Military/tactical context: multilingual personnel workflows support coalition and
joint operations, while deterministic offline outputs preserve readiness command
insight in disconnected deployments.

## Adapter

- Class: `HorillaAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.horilla`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
