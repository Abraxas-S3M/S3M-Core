# GLAWS (SpearBot) integration

S3M military integration wrapper for
[GLAWS](https://github.com/westpoint-robotics/GLAWS).

## Military/Tactical context

This adapter supports ethics and policy-gate rehearsals for autonomous ground
weapons research prototypes in isolated military test environments.

## Adapter contract

- Class: `GlawsspearbotAdapter`
- Base class: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.military.glaws-spearbot`

## Behavior

- Reads metadata from `manifest.yaml`
- Validates local binary/path availability
- Returns deterministic fixture data in airgapped mode
- Performs no external API calls
