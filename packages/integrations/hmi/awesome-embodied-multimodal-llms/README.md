# Awesome-Embodied-Multimodal-LLMs Integration (HMI Domain)

S3M wrapper for [Awesome-Embodied-Multimodal-LLMs](https://github.com/tulerfeng/Awesome-Embodied-Multimodal-LLMs).

## Tactical purpose

This adapter enables offline review of embodied multimodal LLM progress for mission-oriented Human-Machine Teaming model pipelines.

## Adapter class

- `AwesomeEmbodiedMultimodalLlmsAdapter`
- `integration_id = "awesome-embodied-multimodal-llms"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.awesome-embodied-multimodal-llms`

## Airgapped behavior

When `mode="airgapped"`, `execute()` serves deterministic fixture content from `fixtures/sample_response.json`.
