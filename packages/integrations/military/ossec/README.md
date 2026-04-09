# OSSEC Integration

S3M military-domain wrapper for **OSSEC**.

## Military / Tactical Context
This adapter supports host-based intrusion detection and endpoint vulnerability
triage so cyber defense teams can rehearse containment plans offline.

## Adapter Class
- `OssecAdapter`
- `integration_id = "ossec"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local OSSEC binaries and configured paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
