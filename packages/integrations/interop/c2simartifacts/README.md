# C2SIMArtifacts integration

This wrapper provides a sovereign S3M interoperability integration for **C2SIMArtifacts**.

## Tactical role

Military/tactical context: command-and-control integration teams use this adapter
to validate C2SIM schemas and reference artifacts during coalition interoperability
rehearsals inside disconnected mission networks.

## Adapter

- Class: `C2simartifactsAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.interop.c2simartifacts`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local schema-tool availability and returns readiness metadata.
- No external API calls are performed.
