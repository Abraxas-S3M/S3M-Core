"""S3M Sparse Mixture-of-Experts for CPU-efficient deployment."""

from .cpu_moe import ExpertRouter, MoEConfig, MoEInferenceEngine, SparseMoELayer

__all__ = ["SparseMoELayer", "MoEConfig", "ExpertRouter", "MoEInferenceEngine"]
