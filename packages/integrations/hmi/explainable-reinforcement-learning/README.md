# explainable-reinforcement-learning Integration (HMI Domain)

S3M wrapper for [explainable-reinforcement-learning](https://github.com/observer4599/explainable-reinforcement-learning).

## Tactical purpose

This adapter helps human-machine teaming cells retrieve explainable RL literature for mission policy audit, commander briefings, and rules-of-engagement validation.

## Adapter class

- `ExplainableReinforcementLearningAdapter`
- `integration_id = "explainable-reinforcement-learning"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.explainable-reinforcement-learning`

## Airgapped behavior

In airgapped mode, `execute()` serves `fixtures/sample_response.json` to maintain deterministic offline decision-support analysis.
