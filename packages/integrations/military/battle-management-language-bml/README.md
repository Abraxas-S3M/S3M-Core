# Battle Management Language (BML) Integration

S3M military-domain wrapper for **Battle Management Language (BML)** resources.

## Military / Tactical Context
This adapter supports coalition and joint-force C4I simulation drills where
orders and reports must remain interoperable across heterogeneous systems.

## Adapter Class
- `BattleManagementLanguagebmlAdapter`
- `integration_id = "battle-management-language-bml"`
- `domain = "military"`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
