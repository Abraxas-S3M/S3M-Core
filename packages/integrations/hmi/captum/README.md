# Captum Integration (HMI Domain)

S3M wrapper for [Captum](https://github.com/pytorch/captum).

## Tactical purpose

This adapter supports explainability for AI-assisted military decisions by standardizing how attribution outputs are retrieved in both connected and airgapped command environments.

## Adapter class

- `CaptumAdapter`
- `integration_id = "captum"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.captum`

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json`, enabling deterministic interpretation checks during offline mission rehearsal and validation.
