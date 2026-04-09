# Streamlit-Cybersecurity-Dashboard Integration

S3M wrapper for
[Streamlit-Cybersecurity-Dashboard](https://github.com/ajitagupta/streamlit-cybersecurity-dashboard).

## Military / tactical purpose

This adapter supports cyber defense command by standardizing security dashboard
outputs for mission operations in disconnected environments.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` confirms local runtime availability.
- `execute()` returns fixture data while airgapped.
- Online mode intentionally avoids outbound calls in sovereign deployments.

## Files

- `adapter.py` - `StreamlitCybersecurityDashboardAdapter`
- `manifest.yaml` - integration metadata
- `fixtures/sample_response.json` - representative airgapped payload
