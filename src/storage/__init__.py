"""
Storage layer interfaces for mission-critical artifact logistics.

Tactical context:
    This package standardizes secure movement of model payloads between
    training infrastructure and the sovereign vault so edge units can
    recover combat-ready runtimes without internet dependency.
"""

from .object_storage import (
    ObjectStorageChecksumError,
    ObjectStorageConfigError,
    ObjectStorageConnector,
    ObjectStorageError,
    ObjectStorageOperationError,
)
from .vault_paths import VAULT_PATHS

# Backward-compatible aliases for transition from legacy storage naming.
B2Connector = ObjectStorageConnector
B2ConnectorError = ObjectStorageError
B2ConfigurationError = ObjectStorageConfigError
B2OperationError = ObjectStorageOperationError
B2ChecksumError = ObjectStorageChecksumError

__all__ = [
    "ObjectStorageChecksumError",
    "ObjectStorageConfigError",
    "ObjectStorageConnector",
    "ObjectStorageError",
    "ObjectStorageOperationError",
    "B2ChecksumError",
    "B2ConfigurationError",
    "B2Connector",
    "B2ConnectorError",
    "B2OperationError",
    "VAULT_PATHS",
]
