# OSINT-Framework Integration

S3M wrapper for the [OSINT-Framework](https://github.com/lockfale/OSINT-Framework) repository.

## Military/Tactical Context

This adapter exposes a standardized interface for intelligence and OSINT
brief generation so mission staff can operate in sovereign, disconnected
environments without depending on live external services.

## Behavior

- **Airgapped mode**: returns `fixtures/sample_response.json`.
- **Online mode**: validates local dependencies and returns a structured
  orchestrator handoff response.

## Adapter Class

- Module: `packages.integrations.intel.osint-framework.adapter`
- Class: `OsintFrameworkAdapter`
- Integration ID: `osint-framework`
- Domain: `intel`
