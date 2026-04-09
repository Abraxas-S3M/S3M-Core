# MISP-Dashboard Integration

S3M wrapper for [MISP-Dashboard](https://github.com/MISP/misp-dashboard).

## Military / tactical purpose

This integration standardizes live threat-intel dashboard data used for SOC and
coalition interoperability awareness while preserving sovereign offline control.

## Behavior

- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime/tool availability.
- `execute()` returns fixture data in airgapped mode.
- Online mode performs no external API calls in this wrapper.

## Files

- `adapter.py` - `MispDashboardAdapter`
- `manifest.yaml` - integration metadata
- `fixtures/sample_response.json` - airgapped response payload
