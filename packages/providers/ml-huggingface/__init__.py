"""Hugging Face provider integration for S3M model management."""

from .adapter import HuggingFaceAdapter
from .config import HuggingFaceConfig, S3M_MODEL_REGISTRY
from .normalizer import HuggingFaceNormalizer

__all__ = ["HuggingFaceAdapter", "HuggingFaceConfig", "HuggingFaceNormalizer", "S3M_MODEL_REGISTRY"]
