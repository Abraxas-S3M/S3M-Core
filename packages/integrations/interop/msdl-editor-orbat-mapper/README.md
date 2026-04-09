# msdl-editor (orbat-mapper) Integration

S3M wrapper for MSDL editor and ORBAT mapper references.

## Military/tactical context

Scenario editors in coalition exercises must maintain consistent force
structures and initialization artifacts across partner systems. This wrapper
provides deterministic MSDL/ORBAT metadata in airgapped environments.

## Adapter class

- Module: `packages/integrations/interop/msdl-editor-orbat-mapper/adapter.py`
- Class: `MsdlEditororbatMapperAdapter`
- Integration ID: `msdl-editor-orbat-mapper`
- Domain: `interop`

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local editor runtime/path availability.
- `execute()` returns fixture data when running airgapped.
