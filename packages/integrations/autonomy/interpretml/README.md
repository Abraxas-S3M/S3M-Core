# InterpretML Integration (Autonomy Domain)

S3M wrapper for [InterpretML](https://github.com/interpretml/interpret).

## Tactical purpose

This adapter provides interpretable model outputs so mission teams can audit decision rationale before autonomy actions are authorized in high-stakes operations.

## Adapter class

- `InterpretmlAdapter`
- `integration_id = "interpretml"`
- `domain = "autonomy"`
- logger: `s3m.integrations.autonomy.interpretml`

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json` to keep interpretability checks operational without external package/network dependencies.

## Example

```python
from packages.integrations.autonomy.interpretml import InterpretmlAdapter

adapter = InterpretmlAdapter(mode="airgapped")
report = adapter.execute({"action": "global_explanation"})
```
