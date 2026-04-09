# wazuh-soc-enterprise Integration

S3M cyber integration wrapper for the
[wazuh-soc-enterprise](https://github.com/brunoflausino/wazuh-soc-enterprise)
repository.

## Military/Tactical Context

The adapter helps cyber defense command elements maintain common operational
awareness across enterprise SOC tooling while preserving deterministic behavior
under airgap and denied-connectivity mission profiles.

## Behavior

- Loads metadata from `manifest.yaml`
- Verifies local availability of key SOC components
- Returns stable fixture telemetry in airgapped mode
- Enforces strict action and scope validation for secure execution
