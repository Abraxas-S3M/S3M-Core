# security-onion Integration

Security Onion integration wrapper for S3M cyber defense operations. In airgapped mode it returns deterministic hunt telemetry fixtures for tactical rehearsal and mission planning.

## Tactical Use

- Enables deterministic cyber workflow simulation for sovereign deployments.
- Supports airgapped execution by returning local fixture data.
- Provides local availability checks before live-mode operations.

## Adapter Class

- Module: `packages.integrations.cyber.security-onion.adapter`
- Class: `SecurityOnionAdapter`
- Integration ID: `security-onion`
- Domain: `cyber`

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.cyber.security-onion.adapter")
adapter = module.SecurityOnionAdapter(mode="airgapped")
output = adapter.execute({"operation": "status"})
print(output["source"])  # fixture
```
