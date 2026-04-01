"""Certificate-based auth placeholders for mTLS provider integrations."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from base.auth_strategy import AuthStrategy
from errors.integration_errors import AuthenticationError
from .secret_provider import SecretProvider


class CertificateAuth(AuthStrategy):
    """Represents client certificate configuration for mTLS-capable providers."""

    def __init__(
        self,
        cert_path_key: str,
        key_path_key: str,
        secret_provider: Optional[SecretProvider] = None,
    ) -> None:
        self.cert_path_key = cert_path_key
        self.key_path_key = key_path_key
        self.secret_provider = secret_provider or SecretProvider()

    def apply(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        cert_path = self.secret_provider.get(self.cert_path_key)
        key_path = self.secret_provider.get(self.key_path_key)
        if not cert_path or not key_path:
            raise AuthenticationError("Certificate auth requires cert and key paths")
        out_headers = dict(headers or {})
        out_headers["X-Client-Cert-Configured"] = "true"
        return out_headers, dict(params or {})

    def validate(self) -> bool:
        return bool(self.secret_provider.get(self.cert_path_key) and self.secret_provider.get(self.key_path_key))
