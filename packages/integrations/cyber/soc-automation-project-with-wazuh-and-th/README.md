# SOC Automation Project with wazuh and thehive (medium references) Integration

SOC automation wrapper for Wazuh + TheHive community workflows. Designed for sovereign, offline cyber operations with reproducible fixture outputs.

## Tactical Use

- Enables deterministic cyber workflow simulation for sovereign deployments.
- Supports airgapped execution by returning local fixture data.
- Provides local availability checks before live-mode operations.

## Adapter Class

- Module: `packages.integrations.cyber.soc-automation-project-with-wazuh-and-th.adapter`
- Class: `SocAutomationProjectWithAdapter`
- Integration ID: `soc-automation-project-with-wazuh-and-th`
- Domain: `cyber`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.cyber.soc-automation-project-with-wazuh-and-th.adapter")
adapter = module.SocAutomationProjectWithAdapter(mode="airgapped")
output = adapter.execute({"operation": "status"})
print(output["source"])  # fixture
```
