# Awesome-OSINT-For-Everything Integration

S3M adapter wrapper for [Awesome-OSINT-For-Everything](https://github.com/Astrosp/Awesome-OSINT-For-Everything) in the intelligence domain.

## Tactical purpose

This wrapper exposes a curated OSINT tool index to accelerate collection planning for military intelligence teams operating in sovereign and disconnected deployments.

## Capabilities

- Reads metadata from `manifest.yaml` for integration discovery.
- Validates local runtime/tooling readiness in online mode.
- Returns deterministic fixture data in airgapped mode.

## Airgapped behavior

When configured for `airgapped` mode, `execute()` returns `fixtures/sample_response.json` and avoids external requests.
