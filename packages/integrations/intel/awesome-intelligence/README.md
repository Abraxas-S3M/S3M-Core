# awesome-intelligence Integration

S3M wrapper for the `awesome-intelligence` curated resources integration.

## Military/tactical context

Mission intelligence teams need vetted OSINT references they can use without
direct internet access during deployed operations. This adapter provides a
uniform interface with deterministic fixture output for airgapped execution.

## Adapter

- Module: `packages.integrations.intel.awesome-intelligence.adapter`
- Class: `AwesomeIntelligenceAdapter`
- Integration ID: `awesome-intelligence`
- Domain: `intel`

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local tool/repository availability
- Returns realistic fixture responses in airgapped mode
- Performs defensive input validation on execution parameters
