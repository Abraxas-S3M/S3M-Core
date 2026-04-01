"""OAuth2 client credentials authentication for provider APIs."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

from integration_sdk.base.auth_strategy import AuthStrategy
from integration_sdk.errors.integration_errors import AuthenticationError
from integration_sdk.auth.secret_provider import SecretProvider


class OAuth2Auth(AuthStrategy):
    """Client-credentials OAuth2 flow with cached token support."""

    def __init__(
        self,
        token_url: Optional[str],
        client_id_key: str,
        client_secret_key: str,
        scope: Optional[str] = None,
        secret_provider: Optional[SecretProvider] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.token_url = token_url
        self.client_id_key = client_id_key
        self.client_secret_key = client_secret_key
        self.scope = scope
        self.secret_provider = secret_provider or SecretProvider()
        self.timeout_seconds = timeout_seconds
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _cached_valid(self) -> bool:
        return bool(self._access_token and time.time() < (self._token_expires_at - 5.0))

    def _fetch_token(self) -> str:
        if self._cached_valid():
            return self._access_token or ""

        client_id = self.secret_provider.get(self.client_id_key)
        client_secret = self.secret_provider.get(self.client_secret_key)
        if not client_id or not client_secret:
            raise AuthenticationError("OAuth2 client credentials are missing")

        if not self.token_url:
            static_token = self.secret_provider.get("OAUTH2_ACCESS_TOKEN")
            if not static_token:
                raise AuthenticationError("token_url is not set and no static OAuth2 token is configured")
            self._access_token = static_token
            self._token_expires_at = time.time() + 300.0
            return static_token

        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if self.scope:
            payload["scope"] = self.scope

        body = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            self.token_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                token_body = response.read().decode("utf-8")
                parsed = json.loads(token_body)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AuthenticationError(f"OAuth2 token request failed: {exc}") from exc

        token = parsed.get("access_token")
        expires_in = float(parsed.get("expires_in", 300))
        if not token:
            raise AuthenticationError("OAuth2 token response missing access_token")

        self._access_token = token
        self._token_expires_at = time.time() + max(expires_in, 30.0)
        return token

    def apply(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        out_headers = dict(headers or {})
        out_params = dict(params or {})
        out_headers["Authorization"] = f"Bearer {self._fetch_token()}"
        return out_headers, out_params

    def validate(self) -> bool:
        return bool(self.secret_provider.get(self.client_id_key) and self.secret_provider.get(self.client_secret_key))
