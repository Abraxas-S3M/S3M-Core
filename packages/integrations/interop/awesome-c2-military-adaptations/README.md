# awesome-c2 (military adaptations) Integration

S3M wrapper for curated awesome-style command-and-control interoperability
resources and military adaptation references.

## Military/tactical context

Joint and coalition planners need quickly accessible, vetted C2 interoperability
references for modernization and exercise planning in disconnected environments.
This adapter provides deterministic fixture-backed responses for sovereign use.

## Adapter

- Module: `packages.integrations.interop.awesome-c2-military-adaptations.adapter`
- Class: `AwesomeC2militaryAdaptationsAdapter`
- Integration ID: `awesome-c2-military-adaptations`
- Domain: `interop`

## Behavior

- Loads metadata from `manifest.yaml`
- Validates local mirror/tool availability without external API calls
- Returns realistic fixture payloads in airgapped mode
- Applies defensive validation for operator-supplied parameters
