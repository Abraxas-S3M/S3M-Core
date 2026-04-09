# py_trees Integration

S3M autonomy wrapper for [`py_trees`](https://github.com/splintered-reality/py_trees).

## Tactical Purpose

Provides a consistent contract for Python behavior-tree decision flows used by autonomous edge agents during mission execution.

## Airgapped Operation

- `mode="airgapped"` returns deterministic fixture data from `fixtures/sample_response.json`.
- External network calls are not used.

## Adapter Class

- `PyTreesAdapter`
- `integration_id = "py-trees"`
- `domain = "autonomy"`
