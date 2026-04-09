# UAVs_Meet_LLMs Integration (HMI Domain)

S3M wrapper for [UAVs_Meet_LLMs](https://github.com/Hub-Tian/UAVs_Meet_LLMs).

## Tactical purpose

This adapter supports human-machine teaming for low-altitude UAV missions where
operators need explainable vision-language recommendations before approving
mission-critical actions.

## Adapter class

- `UavsMeetLlmsAdapter`
- `integration_id = "uavs-meet-llms"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.uavs-meet-llms`

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` so mission rehearsal remains deterministic on
isolated infrastructure.
