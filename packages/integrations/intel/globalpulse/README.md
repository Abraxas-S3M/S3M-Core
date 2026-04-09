# globalpulse Integration

S3M wrapper for the [globalpulse](https://github.com/ntamero/globalpulse) repository.

## Military/Tactical Context

This adapter exposes a standardized interface for intelligence and OSINT
brief generation so mission staff can operate in sovereign, disconnected
environments without depending on live external services.

## Behavior

- **Airgapped mode**: returns `fixtures/sample_response.json`.
- **Online mode**: validates local dependencies and returns a structured
  orchestrator handoff response.

## Adapter Class

- Module: `packages.integrations.intel.globalpulse.adapter`
- Class: `GlobalpulseAdapter`
- Integration ID: `globalpulse`
- Domain: `intel`
