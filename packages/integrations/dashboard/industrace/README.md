# Industrace

S3M dashboard integration wrapper for **Industrace**.

## Tactical Purpose
This wrapper provides a uniform integration contract so mission operators can
query dashboard capabilities in denied or disconnected environments without
reaching external APIs.

## Source
- Repository: https://github.com/industrace/industrace
- License: MIT

## Airgapped Mode
When `S3M_AIRGAPPED=true` (or `mode="airgapped"`), `execute()` returns the
fixture at `fixtures/sample_response.json`.

## Online/Local Mode
The adapter does not call external services. It only validates local
availability using either:
1. A local path environment variable (`INDUSTRACE_PATH` or `S3M_INDUSTRACE_PATH`), or
2. Presence of a fallback runtime binary on the host.

## Example
```python
import importlib

module = importlib.import_module("packages.integrations.dashboard.industrace.adapter")
adapter_cls = getattr(module, "IndustraceAdapter")
adapter = adapter_cls(mode="airgapped")
print(adapter.execute({"operation": "status"}))
```
