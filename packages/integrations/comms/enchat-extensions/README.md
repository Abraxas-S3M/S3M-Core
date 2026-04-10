# enchat (extensions) Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for enchat secure communications
flows, including ephemeral encrypted terminal chat and blind relay status.

## Military/Tactical Context
Forward elements require low-signature, resilient messaging paths that continue
to function during infrastructure denial. This wrapper exposes comms readiness
signals so mission controllers can verify secure relay posture before operations.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Validation
`validate_availability()` checks local configured runtime paths/binaries and
known enchat CLI command candidates.

## Example
```python
import importlib.util
from pathlib import Path

adapter_path = Path("packages/integrations/comms/enchat-extensions/adapter.py").resolve()
spec = importlib.util.spec_from_file_location("s3m_enchat_adapter", adapter_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

adapter = module.EnchatextensionsAdapter(mode="airgapped")
result = adapter.execute({"operation": "relay_status", "session_id": "session-tf-spear-19"})
```
