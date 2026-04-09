# PantheonRL Integration

S3M adapter for [PantheonRL](https://github.com/Stanford-ILIAD/PantheonRL) in the autonomy domain.

## Tactical purpose

This wrapper supports self-play and adversarial MARL rehearsal for military red-vs-blue decision training.

## Capabilities

- Unified adapter interface for PantheonRL workflows
- Local availability checks for `pantheonrl` and `stable_baselines3`
- Offline fixture responses for airgapped mission systems

## Airgapped behavior

Airgapped execution returns `fixtures/sample_response.json` so tactical evaluation pipelines stay deterministic without internet access.
