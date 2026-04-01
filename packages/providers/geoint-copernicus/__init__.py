"""Copernicus Open Access Hub (ESA Sentinel) provider for S3M.
Free Sentinel-1 SAR, Sentinel-2 optical, Sentinel-3 ocean, Sentinel-5P atmospheric data.
Feeds Phase 15 SAR/maritime detection and Phase 19 geopolitical OSINT."""
from packages.providers.geoint_copernicus.adapter import CopernicusAdapter
from packages.providers.geoint_copernicus.normalizer import CopernicusNormalizer
from packages.providers.geoint_copernicus.config import CopernicusConfig

