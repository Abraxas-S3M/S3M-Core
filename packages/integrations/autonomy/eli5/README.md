# ELI5 Integration (Autonomy Domain)

S3M wrapper for [ELI5](https://github.com/TeamHG-Memex/eli5).

## Tactical purpose

This integration supports mission assurance by producing feature-level classifier explanations that operators can inspect before authorizing autonomous actions.

## Adapter class

- `Eli5Adapter`
- `integration_id = "eli5"`
- `domain = "autonomy"`
- logger: `s3m.integrations.autonomy.eli5`

## Airgapped behavior

When `mode="airgapped"`, `execute()` serves deterministic output from `fixtures/sample_response.json` for offline explainability drills.

## Example

```python
from packages.integrations.autonomy.eli5 import Eli5Adapter

adapter = Eli5Adapter(mode="airgapped")
explanation = adapter.execute({"action": "explain_prediction"})
```
