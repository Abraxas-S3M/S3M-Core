# Enterprise-SOC-Detection-and-Response-Wazuh Integration

S3M cyber integration wrapper for the
[Enterprise-SOC-Detection-and-Response-Wazuh](https://github.com/THeOLdMAn48/Enterprise-SOC-Detection-and-Response-Wazuh)
repository.

## Military/Tactical Context

This adapter supports defensive cyber mission cells with ATT&CK-aligned alert
triage and investigation context while ensuring operations remain functional in
airgapped and degraded communications conditions.

## Behavior

- Loads metadata from `manifest.yaml`
- Checks local Wazuh/SOC tool availability
- Uses deterministic fixture output in airgapped mode
- Validates operator parameters for secure execution
