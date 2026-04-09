# OSINT-BIBLE Integration

S3M wrapper for `OSINT-BIBLE` in the Intelligence & OSINT Briefings domain.
The adapter supplies deterministic fixture responses in airgapped mode and checks local mirror availability in online mode.

## Tactical Use

- Provides methodology references for intelligence production in disconnected theaters.
- Helps analysts maintain repeatable collection and verification pipelines.
- Supports mission-briefing consistency through S3M integration contracts.

## Adapter Class

- Module: `packages.integrations.intel.osint-bible.adapter`
- Class: `OsintBibleAdapter`
- Integration ID: `osint-bible`
- Domain: `intel`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.intel.osint-bible.adapter")
adapter = module.OsintBibleAdapter(mode="airgapped")
response = adapter.execute({"operation": "methodology_matrix"})
print(response["source"])  # fixture
```
