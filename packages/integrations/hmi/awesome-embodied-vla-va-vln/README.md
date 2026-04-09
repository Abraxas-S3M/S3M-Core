# awesome-embodied-vla-va-vln Integration (HMI Domain)

S3M wrapper for [awesome-embodied-vla-va-vln](https://github.com/jonyzhang2023/awesome-embodied-vla-va-vln).

## Tactical purpose

This adapter lets HMI teams curate and review embodied VLA/VLN resources offline for mission-relevant model evaluation.

## Adapter class

- `AwesomeEmbodiedVlaVaAdapter`
- `integration_id = "awesome-embodied-vla-va-vln"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.awesome-embodied-vla-va-vln`

## Airgapped behavior

When `mode="airgapped"`, `execute()` returns deterministic curated-index fixture content from `fixtures/sample_response.json`.
