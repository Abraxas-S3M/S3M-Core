# Legendary_OSINT Integration

S3M wrapper for `Legendary_OSINT` in the Intelligence & OSINT Briefings domain.
It provides deterministic fixture outputs in airgapped mode and local path checks for sovereign deployments.

## Tactical Use

- Supports CTI and investigative workflow planning in denied environments.
- Provides repeatable briefing outputs without external connectivity.
- Keeps integration behavior aligned with S3M adapter contracts.

## Adapter Class

- Module: `packages.integrations.intel.legendary-osint.adapter`
- Class: `LegendaryOsintAdapter`
- Integration ID: `legendary-osint`
- Domain: `intel`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.intel.legendary-osint.adapter")
adapter = module.LegendaryOsintAdapter(mode="airgapped")
response = adapter.execute({"operation": "risk_brief"})
print(response["source"])  # fixture
```
