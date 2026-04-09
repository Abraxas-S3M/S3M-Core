# Wazuh-Rules Integration

Wazuh-Rules integration wrapper for S3M. Provides local rule availability checks and airgapped fixture output for SOC alert engineering exercises.

## Tactical Use

- Enables deterministic cyber workflow simulation for sovereign deployments.
- Supports airgapped execution by returning local fixture data.
- Provides local availability checks before live-mode operations.

## Adapter Class

- Module: `packages.integrations.cyber.wazuh-rules.adapter`
- Class: `WazuhRulesAdapter`
- Integration ID: `wazuh-rules`
- Domain: `cyber`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.cyber.wazuh-rules.adapter")
adapter = module.WazuhRulesAdapter(mode="airgapped")
output = adapter.execute({"operation": "status"})
print(output["source"])  # fixture
```
