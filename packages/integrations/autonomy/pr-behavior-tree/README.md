# pr_behavior_tree Integration

S3M adapter for `pr_behavior_tree`, a lightweight Python behavior-tree library.

## Tactical purpose

This wrapper supports rapid mission-logic prototyping where coroutine behavior
trees are evaluated locally on constrained edge compute nodes.

## Files

- `adapter.py` - `PrBehaviorTreeAdapter` implementation.
- `manifest.yaml` - metadata for registry discovery.
- `fixtures/sample_response.json` - deterministic airgapped execution payload.

## Airgapped behavior

In airgapped mode, the adapter returns fixture output to maintain deterministic
test and rehearsal flows in denied communications environments.

## Online behavior

`validate_availability()` verifies the Python module is importable from the
local runtime and that a Python interpreter is present on the node.
