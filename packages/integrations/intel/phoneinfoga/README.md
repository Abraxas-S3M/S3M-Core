# phoneinfoga Integration

S3M wrapper for the `phoneinfoga` OSINT tool.

## Military/tactical context

Phone-number attribution can support threat triage, target vetting, and force
protection workflows. This adapter enables deterministic airgapped behavior for
training and mission rehearsal on sovereign infrastructure.

## Adapter

- Module: `packages.integrations.intel.phoneinfoga.adapter`
- Class: `PhoneinfogaAdapter`
- Integration ID: `phoneinfoga`
- Domain: `intel`

## Capabilities

- Loads metadata from `manifest.yaml`
- Validates local binary/repository availability
- Returns fixture-based output in airgapped mode
- Enforces secure input validation on execution params
