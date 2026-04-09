# Arabic-Abstractive-Summarization Integration

S3M wrapper for `Arabic-Abstractive-Summarization` in the Intelligence & OSINT Briefings domain.
The adapter supports deterministic fixture output in airgapped mode and local runtime checks in online mode.

## Tactical Use

- Condenses Arabic source material into mission-ready summary form.
- Keeps command-briefing workflows active in disconnected operations.
- Enforces standardized adapter behavior for S3M orchestration layers.

## Adapter Class

- Module: `packages.integrations.intel.arabic-abstractive-summarization.adapter`
- Class: `ArabicAbstractiveSummarizationAdapter`
- Integration ID: `arabic-abstractive-summarization`
- Domain: `intel`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.intel.arabic-abstractive-summarization.adapter")
adapter = module.ArabicAbstractiveSummarizationAdapter(mode="airgapped")
response = adapter.execute({"operation": "summarize"})
print(response["source"])  # fixture
```
