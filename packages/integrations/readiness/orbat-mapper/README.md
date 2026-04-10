# orbat-mapper Integration

S3M wrapper for the [orbat-mapper](https://github.com/orbat-mapper/orbat-mapper) repository.

## Military/Tactical Context

This adapter converts ORBAT visualization outputs into readiness analytics so
commanders can detect understrength formations and staffing pressure in
airgapped mission environments.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks configured local path or runtime hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
- Online mode keeps execution local and avoids external API calls.

## Adapter Class

- Module: `packages.integrations.readiness.orbat-mapper.adapter`
- Class: `OrbatMapperAdapter`
- Integration ID: `orbat-mapper`
- Domain: `readiness`
