# Metasploit Integration

S3M military-domain wrapper for **Metasploit**.

## Military / Tactical Context
This adapter supports authorized exploit-path validation during mission cyber
assurance exercises so defenders can measure exposure before adversaries do.

## Adapter Class
- `MetasploitAdapter`
- `integration_id = "metasploit"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local Metasploit binaries and configured paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
