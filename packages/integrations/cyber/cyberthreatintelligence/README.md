# CyberThreatIntelligence Integration Wrapper

This package provides an S3M `IntegrationAdapter` wrapper for
[CyberThreatIntelligence](https://github.com/Knoxpix/CyberThreatIntelligence).

## Military/tactical context

Cyber defense watch teams require a consistent and sovereign-safe interface to
threat-intelligence snapshots. This wrapper enables SOC operators to access a
normalized CTI view in both online and airgapped operating conditions.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local availability without external API calls
- Returns realistic fixture data in airgapped mode
- Enforces basic input validation for secure execution

## Example

```python
from packages.integrations.cyber.cyberthreatintelligence import CyberthreatintelligenceAdapter

adapter = CyberthreatintelligenceAdapter(mode="airgapped")
result = adapter.execute({"view": "dashboard", "limit": 10})
print(result["operation_brief"]["watch_condition"])
```
