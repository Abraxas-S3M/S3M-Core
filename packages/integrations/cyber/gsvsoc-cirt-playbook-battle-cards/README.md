# gsvsoc_cirt-playbook-battle-cards Integration Wrapper

This wrapper integrates the [gsvsoc_cirt-playbook-battle-cards](https://github.com/guardsight/gsvsoc_cirt-playbook-battle-cards) repository into S3M.

## Military/Tactical Context

The adapter exposes concise battle cards that help defenders execute immediate countermeasures during active compromise scenarios where response speed is critical.

## Capabilities

- Manifest-based metadata loading
- Airgapped fixture responses for deterministic offline operation
- Local repository availability checks
- Query and threat-family filtering for battle card retrieval

## Configuration

- `GSVSOC_CIRT_PLAYBOOK_BATTLE_CARDS_REPO_PATH` or `S3M_GSVSOC_CIRT_PLAYBOOK_BATTLE_CARDS_REPO_PATH`
- `INTEGRATION_VENDOR_ROOT` or `S3M_INTEGRATION_VENDOR_ROOT`
- `S3M_AIRGAPPED=true` for fixture-only mode

