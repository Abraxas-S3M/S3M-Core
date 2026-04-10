# Autonomous_UAVs_Swarm_Mission Integration

S3M swarm-domain wrapper for **Autonomous_UAVs_Swarm_Mission**.

## Military / Tactical Context
This adapter supports coordinated quadcopter swarm mission rehearsal for ISR and
patrol coverage with mission continuity during vehicle loss or communication
degradation.

## Adapter Class
- `AutonomousUavsSwarmMissionAdapter`
- `integration_id = "autonomous-uavs-swarm-mission"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.autonomous-uavs-swarm-mission`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries/modules/configured paths only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
