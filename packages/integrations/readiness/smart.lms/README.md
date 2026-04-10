# Smart.LMS integration

This wrapper provides a sovereign S3M readiness integration for **Smart.LMS**.

## Tactical role

Military/tactical context: force-generation staff can track course completion,
recertification windows, and training deficits while operating in disconnected
or contested environments.

## Adapter

- Class: `SmartlmsAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.smart.lms`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
