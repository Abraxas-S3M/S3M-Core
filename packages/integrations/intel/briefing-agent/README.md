# briefing-agent Integration

S3M adapter wrapper for [briefing-agent](https://github.com/alexnix300/briefing-agent) in the intelligence domain.

## Tactical purpose

This wrapper provides a controlled interface for multi-agent briefing pipelines used to support command-level intelligence synthesis.

## Capabilities

- Reads adapter metadata from `manifest.yaml`.
- Validates local runtime readiness without external API dependencies.
- Uses fixture data to support deterministic airgapped operation.

## Airgapped behavior

With `mode="airgapped"`, `execute()` returns `fixtures/sample_response.json` and avoids network calls.
