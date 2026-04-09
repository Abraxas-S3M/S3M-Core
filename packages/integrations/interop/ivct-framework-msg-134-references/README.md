# IVCT_Framework (MSG-134 references) Integration

S3M wrapper for IVCT/MSG-134 interoperability verification references.

## Military/tactical context

Coalition exercises require repeatable verification gates to confirm HLA, DIS,
and C2SIM conformance before mission simulation execution. This adapter keeps
that workflow deterministic in sovereign airgapped environments.

## Adapter class

- Module: `packages/integrations/interop/ivct-framework-msg-134-references/adapter.py`
- Class: `IvctFrameworkmsg134Adapter`
- Integration ID: `ivct-framework-msg-134-references`
- Domain: `interop`

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local IVCT toolchain prerequisites.
- `execute()` returns fixture-backed certification output in airgapped mode.
