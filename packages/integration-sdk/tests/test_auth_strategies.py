import os

import pytest

from integration_sdk.auth.api_key_auth import APIKeyAuth
from integration_sdk.auth.no_auth import NoAuth
from integration_sdk.auth.oauth2_auth import OAuth2Auth
from integration_sdk.auth.secret_provider import SecretProvider


def test_secret_provider_env_read(monkeypatch):
    monkeypatch.setenv("S3M_TEST_KEY", "value-123")
    provider = SecretProvider(prefix="S3M")
    assert provider.get("TEST_KEY") == "value-123"
    assert provider.has("TEST_KEY") is True


def test_secret_provider_missing_returns_none(monkeypatch):
    monkeypatch.delenv("S3M_MISSING_KEY", raising=False)
    provider = SecretProvider(prefix="S3M")
    assert provider.get("MISSING_KEY") is None


def test_api_key_auth_header(monkeypatch):
    monkeypatch.setenv("S3M_MOCK_API_KEY", "abc")
    auth = APIKeyAuth(secret_key_name="MOCK_API_KEY")
    headers, params = auth.apply()
    assert headers["X-API-Key"] == "abc"
    assert params == {}


def test_api_key_auth_bearer(monkeypatch):
    monkeypatch.setenv("S3M_MOCK_API_KEY", "abc")
    auth = APIKeyAuth(secret_key_name="MOCK_API_KEY", use_bearer=True)
    headers, _ = auth.apply()
    assert headers["Authorization"] == "Bearer abc"


def test_no_auth_passthrough():
    auth = NoAuth()
    headers, params = auth.apply(headers={"A": "B"}, params={"q": "1"})
    assert headers["A"] == "B"
    assert params["q"] == "1"


def test_oauth2_auth_static_token(monkeypatch):
    monkeypatch.setenv("S3M_CLIENT_ID", "id")
    monkeypatch.setenv("S3M_CLIENT_SECRET", "secret")
    monkeypatch.setenv("S3M_OAUTH2_ACCESS_TOKEN", "tok")
    auth = OAuth2Auth(token_url=None, client_id_key="CLIENT_ID", client_secret_key="CLIENT_SECRET")
    headers, _ = auth.apply()
    assert headers["Authorization"] == "Bearer tok"
