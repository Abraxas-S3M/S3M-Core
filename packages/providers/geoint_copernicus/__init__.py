"""Copernicus Open Access Hub (ESA Sentinel) provider for S3M.
Free Sentinel-1 SAR, Sentinel-2 optical, Sentinel-3 ocean, Sentinel-5P atmospheric data.
Feeds Phase 15 SAR/maritime detection and Phase 19 geopolitical OSINT.
"""

from .adapter import CopernicusAdapter
from .config import CopernicusConfig
from .normalizer import CopernicusNormalizer

__all__ = ["CopernicusAdapter", "CopernicusConfig", "CopernicusNormalizer"]
