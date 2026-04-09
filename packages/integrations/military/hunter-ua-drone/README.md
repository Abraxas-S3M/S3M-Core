# Hunter-UA-Drone integration

S3M military integration wrapper for
[Hunter-UA-Drone](https://github.com/Ohara124c41/Hunter-UA-Drone).

## Military/Tactical context

This adapter supports sovereign counter-UAS mission rehearsal workflows so
defensive drone operators can validate intercept plans in disconnected
environments.

## Adapter contract

- Class: `HunterUaDroneAdapter`
- Base class: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.military.hunter-ua-drone`

## Behavior

- Reads metadata from `manifest.yaml`
- Validates local runtime availability
- Returns deterministic fixture data in airgapped mode
- Performs no external API calls
