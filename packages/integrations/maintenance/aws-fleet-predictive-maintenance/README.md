# aws-fleet-predictive-maintenance Integration

S3M maintenance wrapper for
[aws-fleet-predictive-maintenance](https://github.com/awslabs/aws-fleet-predictive-maintenance).

## Military / Tactical Context

This adapter standardizes predictive-maintenance signals so commanders can
prioritize repairs, preserve sortie availability, and reduce mission downtime in
contested and disconnected theaters.

## Adapter Class

- `AwsFleetPredictiveMaintenanceAdapter`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- `integration_id = "aws-fleet-predictive-maintenance"`
- `domain = "maintenance"`
- Logger: `s3m.integrations.maintenance.aws-fleet-predictive-maintenance`

## Airgapped Behavior

In airgapped mode, `execute()` returns deterministic inference-like payloads
from:

- `fixtures/sample_response.json`

No external API calls are performed.
