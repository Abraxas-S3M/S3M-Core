"""
Secret provider abstraction. Reads credentials from:
1. Environment variables (default for S3M)
2. File-based secrets (for Docker secrets / mounted volumes)
3. Stub/mock mode for testing

NEVER stores credentials in code, configs committed to git, or logs.
"""
import os
from typing import Optional


class SecretProvider:
    """Retrieves secrets without exposing them in code or logs."""

    def __init__(self, prefix: str = "S3M"):
        self.prefix = prefix

    def get(self, key: str) -> Optional[str]:
        """Get a secret value. Tries env var first, then file-based secret.
        Key is automatically prefixed: get("MAXAR_API_KEY") checks S3M_MAXAR_API_KEY.
        Returns None if not found — NEVER raises on missing secret."""
        env_key = f"{self.prefix}_{key}"

        # Try environment variable
        value = os.environ.get(env_key)
        if value:
            return value

        # Try file-based secret (Docker secrets pattern)
        secret_path = f"/run/secrets/{env_key.lower()}"
        if os.path.exists(secret_path):
            with open(secret_path, 'r') as f:
                return f.read().strip()

        return None

    def require(self, key: str) -> str:
        """Get a secret, raise if not found."""
        value = self.get(key)
        if value is None:
            raise EnvironmentError(
                f"Required secret {self.prefix}_{key} not found. "
                f"Set environment variable {self.prefix}_{key} or mount at /run/secrets/{self.prefix.lower()}_{key.lower()}"
            )
        return value

    def has(self, key: str) -> bool:
        """Check if a secret exists without retrieving it."""
        return self.get(key) is not None

    def validate_required(self, keys: list) -> dict:
        """Validate multiple required keys. Returns {key: present_bool}."""
        return {key: self.has(key) for key in keys}
