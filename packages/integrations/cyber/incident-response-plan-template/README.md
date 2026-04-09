# incident-response-plan-template integration

## Purpose
This adapter wraps incident response template workflows so cyber command teams
can access response plans and battle-drill checklists in sovereign environments.

## Airgapped behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- In non-airgapped mode, only local template/tool availability checks are done,
  and a simulated response is returned.

## Adapter class
- `IncidentResponsePlanTemplateAdapter`
- `integration_id`: `incident-response-plan-template`
- `domain`: `cyber`
