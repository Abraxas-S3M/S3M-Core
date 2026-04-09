# drone_swarm Integration (Military Domain)

S3M wrapper for [drone_swarm](https://github.com/iamrajee/drone_swarm).

## Tactical purpose

This adapter supports autonomous UAV swarm-network rehearsal so operators can
validate mesh-link resilience and formation control in denied or disconnected
environments.

## Adapter class

- `DroneSwarmAdapter`
- `integration_id = "drone-swarm"`
- `domain = "military"`
- logger: `s3m.integrations.military.drone-swarm`

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` and does not call external services.
