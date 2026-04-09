# Supply-Chain-Performance-Dashboard Integration

S3M wrapper for
[Supply-Chain-Performance-Dashboard](https://github.com/PolinaBurova/Supply-Chain-Performance-Dashboard).

## Military / tactical purpose

This adapter exposes fulfillment, risk, and profitability signals needed for
sustainment command decisions under airgapped operational constraints.

## Behavior

- `get_manifest()` reads `manifest.yaml`.
- `validate_availability()` checks local runtime/tool readiness.
- `execute()` returns fixture-backed results in airgapped mode.
- Online mode remains non-networked for sovereign control.

## Files

- `adapter.py` - `SupplyChainPerformanceDashboardAdapter`
- `manifest.yaml` - integration metadata
- `fixtures/sample_response.json` - airgapped sample response
