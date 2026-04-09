# awesome-geospatial Integration

S3M wrapper for the `awesome-geospatial` interoperability reference collection.

## Military/tactical context

Coalition simulation teams need deterministic guidance on geospatial tooling
that can be used with DIS and C2SIM workflows in disconnected environments.
This wrapper provides a secure adapter contract with fixture-backed responses.

## Adapter class

- Module: `packages/integrations/interop/awesome-geospatial/adapter.py`
- Class: `AwesomeGeospatialAdapter`
- Integration ID: `awesome-geospatial`
- Domain: `interop`

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local path/tool availability.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
