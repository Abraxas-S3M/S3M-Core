# military-ai integration

S3M military integration wrapper for
[military-ai](https://github.com/AI-Guru/military-ai).

## Military/Tactical context

This adapter provides a sovereign interface to curated military AI references so
operators can rehearse model-selection and doctrine mapping workflows in
airgapped command environments.

## Adapter contract

- Class: `MilitaryAiAdapter`
- Base class: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.military.military-ai`

## Behavior

- Loads metadata from `manifest.yaml`
- Validates local curated-resource availability
- Returns deterministic fixture data in airgapped mode
- Performs no external API calls
