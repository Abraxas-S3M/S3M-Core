# AIX360 Integration (HMI Domain)

S3M wrapper for [AIX360](https://github.com/Trusted-AI/AIX360).

## Tactical purpose

This adapter exposes explainability workflows so operators can inspect model
reasoning before mission decisions in high-risk and communication-degraded
theaters.

## Adapter class

- `Aix360Adapter`
- `integration_id = "aix360"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.aix360`

## Airgapped behavior

In airgapped mode, `execute()` returns deterministic fixture output from
`fixtures/sample_response.json` for offline mission assurance drills.
