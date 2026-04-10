# ArmyScripts integration

This wrapper provides a sovereign S3M readiness integration for **ArmyScripts**.

## Tactical role

Military/tactical context: script-driven certification rollups provide rapid
training readiness awareness for commanders preparing units for deployment in
communications-constrained environments.

## Adapter

- Class: `ArmyscriptsAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.armyscripts`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
