# open-dis-java integration

This wrapper provides a sovereign S3M interoperability integration for **open-dis-java**.

## Tactical role

Military/tactical context: C2 and simulation engineers use this adapter to
assess Java-based DIS IEEE-1278 interoperability in disconnected rehearsal and
operational training environments.

## Adapter

- Class: `OpenDisJavaAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.interop.open-dis-java`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local Java runtime/tooling availability and returns readiness metadata.
- No external API calls are performed.
