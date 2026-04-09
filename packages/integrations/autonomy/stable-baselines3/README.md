# stable-baselines3 Integration

S3M adapter for [stable-baselines3](https://github.com/DLR-RM/stable-baselines3) in the autonomy domain.

## Tactical purpose

This wrapper exposes reliable single-agent RL algorithms that can be composed into military mission planning and control loops.

## Capabilities

- Policy training/evaluation metadata via a uniform `execute()` interface
- Local package validation for `stable_baselines3`
- Deterministic fixture return path for airgapped deployments

## Airgapped behavior

Airgapped mode returns `fixtures/sample_response.json`, allowing offline mission rehearsal and CI validation with no external service dependency.
