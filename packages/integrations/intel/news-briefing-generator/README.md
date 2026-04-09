# news-briefing-generator Integration

S3M adapter wrapper for [news-briefing-generator](https://github.com/grbtm/news-briefing-generator) in the intelligence domain.

## Tactical purpose

This wrapper enables local RSS clustering and summarization flows for intelligence staff preparing operational briefs in disconnected deployments.

## Capabilities

- Exposes manifest metadata through `get_manifest()`.
- Performs local runtime validation through `validate_availability()`.
- Returns deterministic fixture output via `execute()` in airgapped mode.

## Airgapped behavior

In `airgapped` mode, the adapter reads and returns `fixtures/sample_response.json` without network dependencies.
