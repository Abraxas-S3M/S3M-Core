# osint_stuff_tool_collection Integration

S3M wrapper for `osint_stuff_tool_collection` in the Intelligence & OSINT Briefings domain.
It provides deterministic fixture output in airgapped mode and local availability checks for sovereign deployments.

## Tactical Use

- Supports offline OSINT source planning before mission execution.
- Preserves repeatable briefing behavior in denied or disconnected networks.
- Aligns catalog retrieval with S3M integration contracts.

## Adapter Class

- Module: `packages.integrations.intel.osint-stuff-tool-collection.adapter`
- Class: `OsintStuffToolCollectionAdapter`
- Integration ID: `osint-stuff-tool-collection`
- Domain: `intel`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.intel.osint-stuff-tool-collection.adapter")
adapter = module.OsintStuffToolCollectionAdapter(mode="airgapped")
response = adapter.execute({"operation": "briefing_stack"})
print(response["source"])  # fixture
```
