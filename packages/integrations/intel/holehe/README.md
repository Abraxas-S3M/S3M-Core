# holehe Integration

S3M wrapper for the `holehe` email footprint OSINT tool.

## Military/tactical context

Identity correlation and account exposure analysis are critical for analyst
triage workflows. This wrapper supports sovereign deployments with secure input
handling and fixture-backed airgapped execution.

## Adapter

- Module: `packages.integrations.intel.holehe.adapter`
- Class: `HoleheAdapter`
- Integration ID: `holehe`
- Domain: `intel`

## Capabilities

- Loads manifest metadata for discovery
- Checks local availability without external calls
- Returns realistic fixture payloads when airgapped
- Enforces input validation to reduce unsafe request handling
