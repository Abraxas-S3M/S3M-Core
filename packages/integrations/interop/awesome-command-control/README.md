# awesome-command-control Integration

S3M wrapper for the [tcostam/awesome-command-control](https://github.com/tcostam/awesome-command-control) repository.

## Military/Tactical Context

This adapter helps planners review command-and-control ecosystem options and map
them into mission simulation stacks while preserving deterministic behavior on
airgapped infrastructure.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic catalog fixtures from `fixtures/sample_response.json`.
- **Online mode**: validates local references/tooling and returns a runtime
  handoff payload for deployment-specific execution.

## Files

- `adapter.py`: `AwesomeCommandControlAdapter`
- `manifest.yaml`: integration metadata
- `fixtures/sample_response.json`: deterministic airgapped response
