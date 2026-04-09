# RiskAnalysisWithGenerativeAIReasoning Integration

S3M wrapper for the
[RiskAnalysisWithGenerativeAIReasoning](https://github.com/bartczernicki/RiskAnalysisWithGenerativeAIReasoning)
repository.

## Military/Tactical Context

This adapter exposes AI-based risk analysis dashboard outputs to mission
command workflows, enabling rapid threat briefings from local document
collections in disconnected environments.

## Behavior

- **Airgapped mode**: returns `fixtures/sample_response.json`.
- **Online mode**: checks local runtime dependencies and returns a structured
  handoff payload for orchestrator-managed execution.

## Files

- `adapter.py`: `RiskanalysiswithgenerativeaireasoningAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: offline fixture payload

