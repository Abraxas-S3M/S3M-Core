# Panopticon AI Integration

S3M dashboard wrapper for [Panopticon AI](https://github.com/Panopticon-AI-team/panopticon), a web-based military simulation dashboard for wargaming and projection workflows.

## Adapter Class

- `PanopticonAiAdapter` (`packages/integrations/dashboard/panopticon-ai/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.dashboard.panopticon-ai`

## Airgapped Operation

When running in airgapped mode, `execute()` returns deterministic fixture data from:

- `fixtures/sample_response.json`

This supports reproducible tactical dashboard validation without network dependency.

## Online Availability Check

`validate_availability()` checks:

1. `PANOPTICON_AI_PATH` / `S3M_PANOPTICON_AI_PATH`
2. `panopticon` or `panopticon-ai` command presence

No external API calls are made.

