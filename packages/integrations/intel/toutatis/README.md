# toutatis Integration

S3M wrapper for the `toutatis` OSINT tool.

## Military/tactical context

Operational intelligence teams often need to fuse multiple open-source traces
under disconnected conditions. This wrapper enables reproducible local behavior
with fixture-backed execution for mission rehearsal and analyst training.

## Adapter

- Module: `packages.integrations.intel.toutatis.adapter`
- Class: `ToutatisAdapter`
- Integration ID: `toutatis`
- Domain: `intel`

## Capabilities

- Loads metadata from `manifest.yaml`
- Checks local tool presence in online mode
- Returns realistic fixture payloads in airgapped mode
- Applies secure parameter validation before execution
