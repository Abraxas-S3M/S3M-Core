# OSINT-War-Room Integration

S3M wrapper for the [OSINT-War-Room](https://github.com/Hue-Jhan/OSINT-War-Room) repository.

## Military/Tactical Context

This adapter adapts tactical war-room views into personnel readiness signals so
operations centers can track fatigue, staffing pressure, and alert priorities
without relying on internet-connected services.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks configured local path or runtime hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
- Online mode provides orchestrator-safe status responses without external calls.

## Adapter Class

- Module: `packages.integrations.readiness.osint-war-room.adapter`
- Class: `OsintWarRoomAdapter`
- Integration ID: `osint-war-room`
- Domain: `readiness`
