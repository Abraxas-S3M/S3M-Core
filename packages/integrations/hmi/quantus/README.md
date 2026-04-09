# Quantus Integration (HMI Domain)

S3M wrapper for [Quantus](https://github.com/understandable-machine-intelligence-lab/Quantus).

## Tactical purpose

This adapter evaluates the quality and robustness of model explanations to help
mission teams identify brittle AI rationale before deployment.

## Adapter class

- `QuantusAdapter`
- `integration_id = "quantus"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.quantus`

## Airgapped behavior

In airgapped mode, `execute()` returns deterministic fixture output from
`fixtures/sample_response.json` for offline readiness assessments.
