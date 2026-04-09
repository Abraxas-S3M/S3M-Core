# awesome-behavior-trees Integration Adapter

Military/tactical context: this wrapper exposes curated behavior-tree references for doctrine and autonomy playbook development in sovereign, airgapped environments.

## Source Repository

- URL: https://github.com/BehaviorTree/awesome-behavior-trees
- License: MIT

## Adapter Class

- `AwesomeBehaviorTreesAdapter` in `adapter.py`
- `integration_id`: `awesome-behavior-trees`
- `domain`: `autonomy`
- Logger: `s3m.integrations.autonomy.awesome-behavior-trees`

## Operational Modes

- **Airgapped**: serves deterministic catalog output from fixture JSON.
- **Online**: checks for local mirrored reference corpus path.

## Primary Entry Point

- `execute(params)` wraps reference listing and curation requests.
