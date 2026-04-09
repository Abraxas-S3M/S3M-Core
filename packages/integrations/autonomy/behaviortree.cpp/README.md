# BehaviorTree.CPP Integration

S3M autonomy wrapper for [`BehaviorTree.CPP`](https://github.com/BehaviorTree/BehaviorTree.CPP).

## Tactical Purpose

Enables standardized behavior-tree mission logic integration for modular autonomous decision policies in disconnected operations.

## Airgapped Operation

- `mode="airgapped"` serves deterministic execution samples from `fixtures/sample_response.json`.
- Runtime avoids external API dependencies.

## Adapter Class

- `BehaviortreecppAdapter`
- `integration_id = "behaviortree.cpp"`
- `domain = "autonomy"`
