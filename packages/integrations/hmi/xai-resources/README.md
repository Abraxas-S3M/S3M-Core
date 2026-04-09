# xai_resources Integration (HMI Domain)

S3M wrapper for [xai_resources](https://github.com/pbiecek/xai_resources).

## Tactical purpose

This adapter provides a curated explainability resource bundle for human-machine teaming programs that need repeatable, auditable transparency workflows in sovereign environments.

## Adapter class

- `XaiResourcesAdapter`
- `integration_id = "xai-resources"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.xai-resources`

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json` to keep mission assurance and training pipelines functional offline.
