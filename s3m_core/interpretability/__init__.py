"""Interpretability components for S3M white-box monitoring."""

from .contrastive_discovery import ContrastiveFeatureDiscovery
from .feature_registry import FeatureSpec, ThreatAlert, ThreatFeatureRegistry
from .gradient_attribution import GradientAttribution
from .hooks import ActivationHookManager
from .sparse_autoencoder import SparseAutoencoder

__all__ = [
    "ActivationHookManager",
    "ContrastiveFeatureDiscovery",
    "FeatureSpec",
    "GradientAttribution",
    "SparseAutoencoder",
    "ThreatAlert",
    "ThreatFeatureRegistry",
]
