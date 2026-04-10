# Employee_Training_Dashboard integration

This wrapper provides a sovereign S3M readiness integration for
**Employee_Training_Dashboard**.

## Tactical role

Military/tactical context: training officers can assess attendance, completion,
and competency gaps for mission-essential skills while disconnected from
external cloud dashboards.

## Adapter

- Class: `EmployeeTrainingDashboardAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.employee-training-dashboard`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local command/tooling availability only.
- No external API calls are performed.
