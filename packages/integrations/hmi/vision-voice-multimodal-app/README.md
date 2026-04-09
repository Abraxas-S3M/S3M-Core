# vision-voice-multimodal-app Integration (HMI Domain)

S3M wrapper for [vision-voice-multimodal-app](https://github.com/EvanGks/vision-voice-multimodal-app).

## Tactical purpose

This adapter enables operators to rehearse multimodal assistant interactions (voice + image + spoken response) while fully airgapped.

## Adapter class

- `VisionVoiceMultimodalAppAdapter`
- `integration_id = "vision-voice-multimodal-app"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.vision-voice-multimodal-app`

## Airgapped behavior

When `mode="airgapped"`, `execute()` returns deterministic fixture data from `fixtures/sample_response.json` for command-post simulation workflows.
