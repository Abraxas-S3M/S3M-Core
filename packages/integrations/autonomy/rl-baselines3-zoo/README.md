# rl-baselines3-zoo Integration (Autonomy Domain)

S3M wrapper for [rl-baselines3-zoo](https://github.com/DLR-RM/rl-baselines3-zoo).

## Tactical purpose

This integration standardizes RL training plan generation so autonomy policy updates can be rehearsed and validated offline before mission rollout.

## Adapter class

- `RlBaselines3ZooAdapter`
- `integration_id = "rl-baselines3-zoo"`
- `domain = "autonomy"`
- logger: `s3m.integrations.autonomy.rl-baselines3-zoo`

## Airgapped behavior

When `mode="airgapped"`, `execute()` returns `fixtures/sample_response.json` to support deterministic training-pipeline testing without internet access.

## Example

```python
from importlib import import_module

adapter_cls = import_module("packages.integrations.autonomy.rl-baselines3-zoo.adapter").RlBaselines3ZooAdapter
adapter = adapter_cls(mode="airgapped")
plan = adapter.execute({"action": "build_training_plan"})
```
