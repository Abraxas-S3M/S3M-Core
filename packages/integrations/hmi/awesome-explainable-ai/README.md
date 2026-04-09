# awesome-explainable-ai Integration Adapter

Military/tactical context: this wrapper provides a mission-safe interface for
retrieving explainable AI references so human-machine teaming operators can
justify autonomous model behavior during denied-connectivity operations.

## Source Repository

- URL: https://github.com/rushrukh/awesome-explainable-ai
- License: MIT

## Adapter Class

- `AwesomeExplainableAiAdapter` in `adapter.py`
- `integration_id`: `awesome-explainable-ai`
- `domain`: `hmi`
- Logger: `s3m.integrations.hmi.awesome-explainable-ai`

## Airgapped Mode

When `S3M_AIRGAPPED=true` (or `mode="airgapped"`), `execute()` returns
deterministic fixture data from:

- `fixtures/sample_response.json`

## Local/Online Mode

This adapter performs no external API calls. It validates local availability by:

1. Checking `AWESOME_EXPLAINABLE_AI_PATH` (or `S3M_AWESOME_EXPLAINABLE_AI_PATH`)
2. Falling back to checking if `git` exists on the host

## Example

```python
import importlib.util
from pathlib import Path

adapter_path = Path("packages/integrations/hmi/awesome-explainable-ai/adapter.py")
spec = importlib.util.spec_from_file_location("hmi_awesome_xai_adapter", adapter_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

adapter = module.AwesomeExplainableAiAdapter(mode="airgapped")
print(adapter.execute({"operation": "xai_frontier_brief"}))
```
