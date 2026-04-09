# Social-Media-OSINT-Tools-Collection Integration

S3M wrapper for `Social-Media-OSINT-Tools-Collection`.

## Military/tactical context

Information operations and social terrain monitoring require consistent tool
references even on disconnected infrastructure. This wrapper provides a
standard interface with airgapped fixture execution for repeatable briefings.

## Adapter

- Module: `packages.integrations.intel.social-media-osint-tools-collection.adapter`
- Class: `SocialMediaOsintToolsAdapter`
- Integration ID: `social-media-osint-tools-collection`
- Domain: `intel`

## Capabilities

- Loads metadata from `manifest.yaml`
- Performs local availability checks
- Returns deterministic fixture data in airgapped mode
- Validates request parameters for secure handling
