# soc-toolkit Integration

S3M cyber integration wrapper for the
[soc-toolkit](https://github.com/phrp720/soc-toolkit) repository.

## Military/Tactical Context

The adapter provides standardized SOC toolkit status and triage context for
defensive cyber mission cells operating in sovereign, disconnected, or
communications-degraded environments.

## Behavior

- Loads metadata from `manifest.yaml`
- Checks whether local SOC toolkit dependencies are available
- Returns deterministic fixture data in airgapped mode
- Enforces strict input validation for mission-safe execution
