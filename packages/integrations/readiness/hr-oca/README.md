# hr (OCA) integration

This wrapper provides a sovereign S3M readiness integration for **hr (OCA)**.

## Tactical role

Military/tactical context: headquarters personnel cells can maintain trusted HR,
training, and payroll readiness snapshots when external enterprise services are
degraded or denied.

## Adapter

- Class: `HrocaAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.hr-oca`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
