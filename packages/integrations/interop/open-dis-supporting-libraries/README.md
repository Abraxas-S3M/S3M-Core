# open-dis supporting libraries Integration

S3M wrapper for open-dis helper components used in interoperability and simulation
data exchange workflows.

## Military/tactical context

Operational simulation cells and command-post trainers need deterministic DIS
coordinate and PDU tooling in disconnected environments. This adapter provides
a sovereign-safe interface that keeps mission rehearsal pipelines functional
when external access is denied.

## Adapter

- Module: `packages.integrations.interop.open-dis-supporting-libraries.adapter`
- Class: `OpenDisSupportingLibrariesAdapter`
- Integration ID: `open-dis-supporting-libraries`
- Domain: `interop`

## Behavior

- Loads discovery metadata from `manifest.yaml`
- Validates local availability via module/command checks or mirrored path
- Returns realistic fixture data in airgapped mode
- Validates and sanitizes input parameters before execution
