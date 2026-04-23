"""Credential vault layer for mission-safe secret handling in S3M."""

from .credential_proxy import CredentialProxy, ProxyResponse, ServiceConfig
from .token_manager import SessionToken, TokenManager, TokenValidation
from .vault_client import DynamicCredential, SecretAccess, VaultClient

__all__ = [
    "CredentialProxy",
    "DynamicCredential",
    "ProxyResponse",
    "SecretAccess",
    "ServiceConfig",
    "SessionToken",
    "TokenManager",
    "TokenValidation",
    "VaultClient",
]
