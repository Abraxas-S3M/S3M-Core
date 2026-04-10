# patternfly integration

This wrapper provides a sovereign S3M readiness integration for **patternfly**.

## Tactical role

Military/tactical context: mission-control UI teams can validate dashboard
component readiness and visual compliance while operating in disconnected
command environments.

## Adapter

- Class: `PatternflyAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.patternfly`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local command/tooling availability only.
- No external API calls are performed.
