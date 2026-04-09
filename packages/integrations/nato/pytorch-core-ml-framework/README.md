# PyTorch (core ML framework) Integration

S3M wrapper for [PyTorch](https://github.com/pytorch/pytorch).

## Military/Tactical Context

This adapter supports sovereign AI model assurance and edge-deployment rehearsal
for NATO-aligned neuro-symbolic and agentic systems when external connectivity
is restricted.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local PyTorch module availability and returns a
  runtime handoff payload for orchestrator-managed execution.

## Files

- `adapter.py`: `PytorchcoreMlFrameworkAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response
