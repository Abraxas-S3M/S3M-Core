# Model-Inference-Deployment Integration

## Purpose

This adapter wraps **Model-Inference-Deployment** metadata for S3M navigation and control workflows.

Military/tactical context: it enables offline comparison of inference runtimes so mission planners can select deterministic model execution paths on disconnected Jetson-class edge compute.

## Adapter Class

- `ModelInferenceDeploymentAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.model-inference-deployment`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: performs local runtime/tooling checks without external API calls

## Manifest

Metadata is defined in `manifest.yaml` and loaded by `get_manifest()`.
