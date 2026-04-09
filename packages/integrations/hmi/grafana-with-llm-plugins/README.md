# Grafana (with LLM plugins) HMI Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Grafana with LLM plugin workflows in the Human-Machine Teaming domain.

## Military/Tactical Context
Supports command-level observability by surfacing OpenTelemetry traces, dashboard health, and LLM plugin signals for mission-critical AI services.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks local Grafana tooling and falls back to fixture validation in airgapped mode.
