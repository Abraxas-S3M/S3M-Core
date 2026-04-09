# awesome-explainable-reinforcement-learning Integration (HMI Domain)

S3M wrapper for [awesome-explainable-reinforcement-learning](https://github.com/Plankson/awesome-explainable-reinforcement-learning).

## Tactical purpose

This adapter supports mission assurance by providing an offline-safe catalog of explainable reinforcement learning references that operators can use to justify autonomous behavior under command oversight.

## Adapter class

- `AwesomeExplainableReinforcementLearningAdapter`
- `integration_id = "awesome-explainable-reinforcement-learni"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.awesome-explainable-reinforcement-learni`

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json` so mission explainability workflows remain operational without internet access.
