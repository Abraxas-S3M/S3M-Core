# Incident-Playbook Integration Wrapper

This wrapper integrates the [Incident-Playbook](https://github.com/austinsonger/Incident-Playbook) repository into S3M cyber-defense workflows.

## Military/Tactical Context

The adapter provides technique-aligned response references so defensive cyber units can quickly counter adversary procedures mapped to MITRE ATT&CK.

## Capabilities

- Loads metadata from `manifest.yaml`
- Validates local readiness with no external API traffic
- Supports deterministic airgapped fixture responses
- Filters fixture and local repository results by search query and MITRE technique

## Configuration

- `INCIDENT_PLAYBOOK_REPO_PATH` or `S3M_INCIDENT_PLAYBOOK_REPO_PATH`
- `INTEGRATION_VENDOR_ROOT` or `S3M_INTEGRATION_VENDOR_ROOT`
- `S3M_AIRGAPPED=true` for fixture mode

