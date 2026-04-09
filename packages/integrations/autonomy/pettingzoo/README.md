# PettingZoo Integration (Autonomy Domain)

S3M wrapper for the [PettingZoo](https://github.com/Farama-Foundation/PettingZoo(maintained) repository.

## Tactical purpose

This integration supports offline rehearsal of cooperative and adversarial multi-agent behaviors before deployment to contested mission zones.

## Adapter class

- `PettingzooAdapter`
- `integration_id = "pettingzoo"`
- `domain = "autonomy"`
- logger: `s3m.integrations.autonomy.pettingzoo`

## Airgapped behavior

When adapter mode is `airgapped`, `execute()` returns `fixtures/sample_response.json` so command workflows remain deterministic without external connectivity.

## Example

```python
from packages.integrations.autonomy.pettingzoo import PettingzooAdapter

adapter = PettingzooAdapter(mode="airgapped")
result = adapter.execute({"action": "list_env_families"})
```
