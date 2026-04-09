# DataScienceInteractivePython Integration

S3M wrapper for the
[DataScienceInteractivePython](https://github.com/GeostatsGuy/DataScienceInteractivePython)
repository.

## Military/Tactical Context

This adapter standardizes interactive dashboard outputs used during analyst
training, mission rehearsal, and data-quality drills in disconnected command
environments.

## Behavior

- **Airgapped mode**: returns `fixtures/sample_response.json`.
- **Online mode**: validates dashboard dependencies and returns an execution
  handoff payload for orchestrator-controlled runtime.

## Files

- `adapter.py`: `DatascienceinteractivepythonAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: offline fixture payload

