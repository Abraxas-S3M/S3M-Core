# dis-tutorial integration

This wrapper provides a sovereign S3M interoperability integration for **dis-tutorial**.

## Tactical role

Military/tactical context: exercise-control and simulation-planning cells use this
adapter to access DIS reference guidance for mission rehearsal without relying on
external connectivity.

## Adapter

- Class: `DisTutorialAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.interop.dis-tutorial`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local tutorial tooling availability and returns readiness metadata.
- No external API calls are performed.
