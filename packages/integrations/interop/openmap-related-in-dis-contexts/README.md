# OpenMap (related in DIS contexts) Integration

S3M wrapper for OpenMap references used in DIS/C2SIM visualization workflows.

## Military/tactical context

Coalition operators need map display interoperability that remains functional in
airgapped command posts. This adapter standardizes how OpenMap-related metadata
is consumed by simulation and command interfaces.

## Adapter class

- Module: `packages/integrations/interop/openmap-related-in-dis-contexts/adapter.py`
- Class: `OpenmaprelatedInDisAdapter`
- Integration ID: `openmap-related-in-dis-contexts`
- Domain: `interop`

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local path/runtime presence.
- `execute()` emits fixture-backed results in airgapped mode.
