# gym-pybullet-drones Integration

S3M autonomy wrapper for [`gym-pybullet-drones`](https://github.com/utiasDSL/gym-pybullet-drones).

## Tactical Purpose

Provides a standardized adapter for quadcopter simulation and rehearsal loops so autonomy behaviors can be evaluated on disconnected edge infrastructure.

## Airgapped Operation

- `mode="airgapped"` returns deterministic fixture data from `fixtures/sample_response.json`.
- No external API calls are performed.

## Adapter Class

- `GymPybulletDronesAdapter`
- `integration_id = "gym-pybullet-drones"`
- `domain = "autonomy"`
