# Employee-Project-Management-Platform integration

This wrapper provides a sovereign S3M readiness integration for
**Employee-Project-Management-Platform**.

## Tactical role

Military/tactical context: readiness planners can review staffing posture,
attendance, and project assignment pressure during mission preparation even in
airgapped operating environments.

## Adapter

- Class: `EmployeeProjectManagementPlatformAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.employee-project-management-platform`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local command/tooling availability only.
- No external API calls are performed.
