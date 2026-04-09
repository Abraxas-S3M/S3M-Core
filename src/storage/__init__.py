"""
Storage layer interfaces for mission-critical artifact logistics.

Tactical context:
    This package standardizes secure movement of model payloads between
    training infrastructure and the sovereign vault so edge units can
    recover combat-ready runtimes without internet dependency.
"""

from .b2_connector import (
    B2ChecksumError,
    B2ConfigurationError,
    B2Connector,
    B2ConnectorError,
    B2OperationError,
)
from .vault_paths import VAULT_PATHS

__all__ = [
    "B2ChecksumError",
    "B2ConfigurationError",
    "B2Connector",
    "B2ConnectorError",
    "B2OperationError",
    "VAULT_PATHS",
]
