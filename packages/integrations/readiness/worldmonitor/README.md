# worldmonitor Integration

S3M wrapper for the [worldmonitor](https://github.com/koala73/worldmonitor) repository.

## Military/Tactical Context

This adapter converts geopolitical dashboard outputs into standardized readiness
signals so personnel planners can sustain force preparation under airgapped,
sovereign mission-network constraints.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks configured local path or runtime hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
- Online mode validates readiness for local orchestration without external calls.

## Adapter Class

- Module: `packages.integrations.readiness.worldmonitor.adapter`
- Class: `WorldmonitorAdapter`
- Integration ID: `worldmonitor`
- Domain: `readiness`
