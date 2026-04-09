# ardupilot Integration (Military Domain)

S3M wrapper for [ardupilot](https://github.com/ArduPilot/ardupilot).

## Tactical purpose

This adapter supports autonomous vehicle mission-readiness checks so field teams
can stage UAV and unmanned-platform operations on sovereign infrastructure.

## Adapter class

- `ArdupilotAdapter`
- `integration_id = "ardupilot"`
- `domain = "military"`
- logger: `s3m.integrations.military.ardupilot`

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` and does not call external services.
