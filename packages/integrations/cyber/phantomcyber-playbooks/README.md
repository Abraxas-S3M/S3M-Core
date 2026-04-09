# phantomcyber/playbooks integration

## Purpose
This adapter wraps the Phantom playbook repository concept for sovereign S3M
deployments that need structured incident response orchestration guidance.

## Airgapped behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- In non-airgapped mode, local tool/path checks are performed and the adapter
  returns a simulated orchestration response.

## Adapter class
- `PhantomcyberplaybooksAdapter`
- `integration_id`: `phantomcyber-playbooks`
- `domain`: `cyber`
