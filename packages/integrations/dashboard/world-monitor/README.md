# World Monitor Integration

S3M wrapper for the [World Monitor](https://github.com/koala73/worldmonitor) dashboard.

## Military / tactical purpose

This integration provides a controlled adapter interface so strategic risk and
conflict summaries can be consumed by command dashboards while maintaining
airgapped operational readiness.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local runtime/tool presence.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
- Online mode never performs external API calls inside this wrapper.

## Files

- `adapter.py` - `WorldMonitorAdapter`
- `manifest.yaml` - integration metadata
- `fixtures/sample_response.json` - airgapped fixture response
