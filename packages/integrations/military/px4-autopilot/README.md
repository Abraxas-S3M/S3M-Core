# PX4-Autopilot Integration (Military Domain)

S3M wrapper for [PX4-Autopilot](https://github.com/PX4/PX4-Autopilot).

## Tactical purpose

This adapter supports sovereign UAV autopilot readiness checks for autonomous
sorties where command systems must remain fully offline-capable.

## Adapter class

- `Px4AutopilotAdapter`
- `integration_id = "px4-autopilot"`
- `domain = "military"`
- logger: `s3m.integrations.military.px4-autopilot`

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` and does not call external services.
