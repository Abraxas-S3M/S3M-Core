# xai (EthicalML) Integration

S3M adapter for the EthicalML `xai` explainability toolkit.

## Tactical purpose

This integration provides local explainability and responsible-ML checks so
command elements can assess model behavior before mission-critical deployment.

## Files

- `adapter.py` - `XaiethicalmlAdapter` implementation.
- `manifest.yaml` - integration metadata for registry discovery.
- `fixtures/sample_response.json` - deterministic airgapped explainability payload.

## Airgapped behavior

In airgapped mode, `execute()` returns fixture output for deterministic model
audit drills without external services.

## Online behavior

`validate_availability()` verifies that the `xai` Python package is importable
from the local runtime.
