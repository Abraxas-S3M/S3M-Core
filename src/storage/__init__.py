"""Storage connectors used by training and promotion pipelines.

Military/tactical context:
Deterministic object-store access patterns keep adapter movement auditable
during contested operations where intermittent connectivity is expected.
"""

from src.storage.b2_connector import B2Connector

__all__ = ["B2Connector"]
