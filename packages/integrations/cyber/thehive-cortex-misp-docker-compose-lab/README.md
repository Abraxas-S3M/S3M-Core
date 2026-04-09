# thehive-cortex-misp-docker-compose-lab Integration

TheHive/Cortex/MISP compose lab wrapper for S3M cyber workflows. Uses deterministic fixtures in airgapped deployments while validating local orchestration prerequisites.

## Tactical Use

- Enables deterministic cyber workflow simulation for sovereign deployments.
- Supports airgapped execution by returning local fixture data.
- Provides local availability checks before live-mode operations.

## Adapter Class

- Module: `packages.integrations.cyber.thehive-cortex-misp-docker-compose-lab.adapter`
- Class: `ThehiveCortexMispDockerAdapter`
- Integration ID: `thehive-cortex-misp-docker-compose-lab`
- Domain: `cyber`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.cyber.thehive-cortex-misp-docker-compose-lab.adapter")
adapter = module.ThehiveCortexMispDockerAdapter(mode="airgapped")
output = adapter.execute({"operation": "status"})
print(output["source"])  # fixture
```
