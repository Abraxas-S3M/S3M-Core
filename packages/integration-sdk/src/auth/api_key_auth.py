"""API key authentication strategies for tactical provider access."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from base.auth_strategy import AuthStrategy
from errors.integration_errors import AuthenticationError
from .secret_provider import SecretProvider


class APIKeyAuth(AuthStrategy):
    """Apply API key as header, bearer token, or query parameter."""

    def __init__(
        self,
        secret_key_name: str,
        secret_provider: Optional[SecretProvider] = None,
        header_name: str = "X-API-Key",
        query_param_name: str = "api_key",
        use_bearer: bool = False,
        as_query_param: bool = False,
    ) -> None:
        self.secret_key_name = secret_key_name
        self.secret_provider = secret_provider or SecretProvider()
        self.header_name = header_name
        self.query_param_name = query_param_name
        self.use_bearer = use_bearer
        self.as_query_param = as_query_param

    def _read_key(self) -> str:
        key = self.secret_provider.get(self.secret_key_name)
        if not key:
            raise AuthenticationError(f"Missing secret for key {self.secret_key_name}")
        return key

    def apply(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        headers_out = dict(headers or {})
        params_out = dict(params or {})
        key = self._read_key()

        if self.as_query_param:
            params_out[self.query_param_name] = key
        elif self.use_bearer:
            headers_out["Authorization"] = f"Bearer {key}"
        else:
            headers_out[self.header_name] = key

        return headers_out, params_out

    def validate(self) -> bool:
        return self.secret_provider.has(self.secret_key_name)
