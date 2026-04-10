# ODIN integration

This wrapper provides a sovereign S3M readiness integration for **ODIN**.

## Tactical role

Military/tactical context: command posts can evaluate personnel coverage and
situational-awareness watch readiness with deterministic offline outputs before
live mission execution.

## Adapter

- Class: `OdinAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.odin`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local command/tooling availability only.
- No external API calls are performed.
