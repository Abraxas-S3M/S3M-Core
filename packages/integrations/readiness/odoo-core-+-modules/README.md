# odoo (core + modules) integration

This wrapper provides a sovereign S3M readiness integration for
**odoo (core + modules)**.

## Tactical role

Military/tactical context: staff planners can combine HR, training, and
multi-company roster data to evaluate force readiness and identify deployment
shortfalls without relying on external ERP services.

## Adapter

- Class: `OdoocoreModulesAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.odoo-core-+-modules`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local command/tooling availability only.
- No external API calls are performed.
