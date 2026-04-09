# alibi Integration (HMI Domain)

S3M wrapper for [alibi](https://github.com/SeldonIO/alibi).

## Tactical purpose

This adapter provides black-box inspection and counterfactual reasoning support
for mission AI outputs that require analyst validation before execution.

## Adapter class

- `AlibiAdapter`
- `integration_id = "alibi"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.alibi`

## Airgapped behavior

In airgapped mode, `execute()` returns fixture data from
`fixtures/sample_response.json` to keep inspection workflows operational in
disconnected deployments.
