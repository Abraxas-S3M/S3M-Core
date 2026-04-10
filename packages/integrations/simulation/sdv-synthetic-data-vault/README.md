# SDV (Synthetic Data Vault) Integration

S3M adapter for [SDV](https://github.com/sdv-dev/SDV) in the `simulation` domain.

## Tactical purpose

This wrapper supports sovereign generation of synthetic mission datasets for
model validation, rehearsal, and analytics when operational records must remain
protected in disconnected military environments.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local SDV runtime availability (path, binary, module probes)
- Returns deterministic fixture output in airgapped mode

## Airgapped behavior

When airgapped mode is enabled, `execute()` returns
`fixtures/sample_response.json` to emulate synthetic data generation outcomes
without requiring external access.
