# Wazuh-SOC-Lab Integration

S3M cyber integration wrapper for the
[Wazuh-SOC-Lab](https://github.com/marxgoo/Wazuh-SOC-Lab) repository.

## Military/Tactical Context

This adapter supports sovereign defensive cyber operations by exposing a
uniform interface for SOC health, alert posture, and triage actions during
contested-network missions where external connectivity can be denied.

## Behavior

- Loads integration metadata from `manifest.yaml`
- Validates local tool availability (`wazuh-manager`, `wazuh-dashboard`,
  `suricata`, or `docker`)
- Returns deterministic fixture output in `airgapped` mode
- Performs strict input validation for requested actions and targets
