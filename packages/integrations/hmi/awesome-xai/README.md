# awesome-xai Integration (HMI Domain)

S3M wrapper for [awesome-xai](https://github.com/altamiracorp/awesome-xai).

## Tactical purpose

This adapter gives human-machine teaming analysts an offline-capable source of explainability methods, papers, and tools used to validate AI recommendations before operational use.

## Adapter class

- `AwesomeXaiAdapter`
- `integration_id = "awesome-xai"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.awesome-xai`

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json` so method selection and assurance reviews continue without network access.
