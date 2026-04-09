# open-dis-python integration

This wrapper provides a sovereign S3M interoperability integration for **open-dis-python**.

## Tactical role

Military/tactical context: simulation and C2 engineering teams use this adapter
to validate DIS v7 packet workflows for mission rehearsal across disconnected
training and operational enclaves.

## Adapter

- Class: `OpenDisPythonAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.interop.open-dis-python`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
