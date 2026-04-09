# open-dis-cpp integration

This wrapper provides a sovereign S3M interoperability integration for **open-dis-cpp**.

## Tactical role

Military/tactical context: high-throughput simulation services can use this
adapter to validate native DIS data exchange behavior during mission rehearsal
without exposing tactical systems to external networks.

## Adapter

- Class: `OpenDisCppAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.interop.open-dis-cpp`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local native-toolchain availability and returns readiness metadata.
- No external API calls are performed.
