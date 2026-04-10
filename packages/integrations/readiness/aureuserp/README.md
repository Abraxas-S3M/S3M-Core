# aureuserp integration

This wrapper provides a sovereign S3M readiness integration for **aureuserp**.

## Tactical role

Military/tactical context: ERP-backed HR and staffing signals help commanders
align force structure, budget commitments, and mission qualification levels in
degraded network conditions.

## Adapter

- Class: `AureuserpAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.aureuserp`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
