# JSBSim Dashboard Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for JSBSim simulation dashboards.

## Military/Tactical Context
Supports mission rehearsal and intercept planning dashboards by surfacing local
flight dynamics, projection confidence, and airframe health summaries.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- This guarantees deterministic responses during disconnected exercises.

## Availability Checks
`validate_availability()` probes local JSBSim availability through the Python
module or CLI binary and falls back to fixture verification when airgapped.

