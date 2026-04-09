"""S3M HMI adapter for awesome-explainable-ai.

Military/tactical context:
This package gives mission teams a deterministic interface for explainable AI
knowledge retrieval during disconnected operations where direct internet access
is denied by policy.
"""

from .adapter import AwesomeExplainableAiAdapter

__all__ = ["AwesomeExplainableAiAdapter"]
