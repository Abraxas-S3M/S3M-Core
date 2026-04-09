# awesome-incident-response Integration Wrapper

This wrapper integrates the [awesome-incident-response](https://github.com/meirwah/awesome-incident-response) repository into S3M.

## Military/Tactical Context

The adapter provides curated defensive tooling references so cyber operators can quickly select mission-appropriate response capabilities while disconnected from the public internet.

## Capabilities

- Manifest-driven metadata via `manifest.yaml`
- Airgapped fixture execution
- Input validation for query, category, and limit parameters
- Optional local repository indexing

## Configuration

- `AWESOME_INCIDENT_RESPONSE_REPO_PATH` or `S3M_AWESOME_INCIDENT_RESPONSE_REPO_PATH`
- `INTEGRATION_VENDOR_ROOT` or `S3M_INTEGRATION_VENDOR_ROOT`
- `S3M_AIRGAPPED=true` for offline fixture mode

