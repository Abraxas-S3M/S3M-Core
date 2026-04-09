# OmniXAI Integration (HMI Domain)

S3M wrapper for [OmniXAI](https://github.com/salesforce/OmniXAI).

## Tactical purpose

This adapter supports multimodal explainability across text, tabular, and
vision inputs so operators can challenge and verify AI outputs before action.

## Adapter class

- `OmnixaiAdapter`
- `integration_id = "omnixai"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.omnixai`

## Airgapped behavior

In airgapped mode, `execute()` returns fixture data from
`fixtures/sample_response.json` for deterministic decision-briefing workflows.
