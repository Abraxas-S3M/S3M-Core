# Awesome-Multimodal-Large-Language-Models-for-UAV Integration (HMI Domain)

S3M wrapper for [Awesome-Multimodal-Large-Language-Models-for-UAV](https://github.com/ZhanYang-nwpu/Awesome-Multimodal-Large-Language-Models-for-UAV-Vision-Language-Perception).

## Tactical purpose

This adapter supports offline curation of UAV-focused multimodal LLM references for reconnaissance perception stack planning.

## Adapter class

- `AwesomeMultimodalLargeLanguageAdapter`
- `integration_id = "awesome-multimodal-large-language-models"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.awesome-multimodal-large-language-models`

## Airgapped behavior

When `mode="airgapped"`, `execute()` serves deterministic fixture content from `fixtures/sample_response.json`.
