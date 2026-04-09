# Supply-Chain-Management-Dashboard Integration

S3M wrapper for
[Supply-Chain-Management-Dashboard](https://github.com/GirishKumarV25/Supply-Chain-Management-Dashboard).

## Military / tactical purpose

This integration supports sustainment planning by standardizing inventory,
supplier, demand, and logistics dashboard outputs for offline command use.

## Behavior

- `get_manifest()` reads `manifest.yaml`.
- `validate_availability()` checks local runtime/tool readiness.
- `execute()` serves fixture output in airgapped mode.
- Online mode is non-networked by policy.

## Files

- `adapter.py` - `SupplyChainManagementDashboardAdapter`
- `manifest.yaml` - integration metadata
- `fixtures/sample_response.json` - airgapped fixture payload
