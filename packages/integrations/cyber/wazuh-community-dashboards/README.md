# Wazuh community dashboards integration

## Purpose
This S3M cyber-domain adapter wraps community dashboard workflows for Wazuh so
operators can inspect SOC posture in tactical environments with intermittent or
denied connectivity.

## Airgapped behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- In non-airgapped mode, the adapter performs local availability checks and
  returns a sovereign-safe simulated response (no external API calls).

## Adapter class
- `WazuhCommunityDashboardsAdapter`
- `integration_id`: `wazuh-community-dashboards`
- `domain`: `cyber`
