# Detectron2 (object detection) Integration

S3M wrapper for [Detectron2](https://github.com/facebookresearch/detectron2).

## Military/Tactical Context

This adapter supports object-detection rehearsal for ISR mission feeds so
analysts can validate model behavior and confidence thresholds in sovereign
airgapped operations.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local Detectron2 module availability and returns a
  runtime handoff payload for orchestrator-managed execution.

## Files

- `adapter.py`: `Detectron2objectDetectionAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response
