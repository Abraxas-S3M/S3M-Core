# NETN references in OpenC2SIM Integration

S3M wrapper for NETN/OpenC2SIM federation agreement references.

## Military/tactical context

Federated coalition simulations require shared agreement artifacts so orders,
reports, and entity updates remain semantically aligned across systems. This
adapter provides deterministic access to NETN references in airgapped mode.

## Adapter class

- Module: `packages/integrations/interop/netn-references-in-openc2sim/adapter.py`
- Class: `NetnReferencesInOpenc2simAdapter`
- Integration ID: `netn-references-in-openc2sim`
- Domain: `interop`

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local NETN/OpenC2SIM references.
- `execute()` returns fixture output for airgapped rehearsal workflows.
