# SOC-Multitool extensions Integration Wrapper

This package provides an S3M `IntegrationAdapter` wrapper for SOC-Multitool
browser extension ecosystems and related investigative helper tooling.

## Military/tactical context

SOC defenders must move quickly from weak telemetry to actionable containment.
This adapter standardizes extension-assisted investigation outputs so analysts
can operate consistently in sovereign and airgapped environments.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Performs local availability checks only (no outbound API calls)
- Returns realistic fixture data for airgapped mode
- Validates execution parameters to reduce unsafe inputs

## Example

```python
import importlib

module = importlib.import_module("packages.integrations.cyber.soc-multitool-extensions.adapter")
adapter = module.SocMultitoolExtensionsAdapter(mode="airgapped")
result = adapter.execute({"workflow": "investigation_assist", "case_id": "SOC-2026-0042", "limit": 5})
print(result["artifacts"][0]["artifact_type"])
```
