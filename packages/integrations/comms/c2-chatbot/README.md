# c2_chatbot Integration

S3M communications-domain wrapper for **c2_chatbot**.

## Military / Tactical Context
This adapter helps sovereign command elements assess and orchestrate secure
communications channels while operating in contested or disconnected theaters.

## Adapter Class
- `C2ChatbotAdapter`
- `integration_id = "c2-chatbot"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.c2-chatbot`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
