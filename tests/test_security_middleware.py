#!/usr/bin/env python3
"""Unit tests for SecurityMiddleware."""

import os
import sys
import time
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.middleware import SecurityMiddleware


def _build_app(config=None):
    app = FastAPI()
    app.add_middleware(SecurityMiddleware, config=config or {})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected():
        return {"result": "ok"}

    @app.get("/echo")
    async def echo(value: str = "ok"):
        return {"value": value}

    return app


class TestSecurityMiddleware(unittest.TestCase):
    def test_middleware_passes_requests_when_auth_disabled(self):
        client = TestClient(_build_app({"auth_enabled": False}))
        resp = client.get("/protected")
        self.assertEqual(resp.status_code, 200)

    def test_middleware_rejects_wrong_api_key_when_auth_enabled(self):
        client = TestClient(_build_app({"auth_enabled": True, "api_key": "secret"}))
        resp = client.get("/protected", headers={"X-API-Key": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_middleware_accepts_correct_api_key(self):
        client = TestClient(_build_app({"auth_enabled": True, "api_key": "secret"}))
        resp = client.get("/protected", headers={"X-API-Key": "secret"})
        self.assertEqual(resp.status_code, 200)

    def test_rate_limiting_blocks_after_threshold(self):
        client = TestClient(
            _build_app(
                {
                    "auth_enabled": False,
                    "rate_limit_enabled": True,
                    "rate_limit_rpm": 2,
                }
            )
        )
        self.assertEqual(client.get("/protected").status_code, 200)
        self.assertEqual(client.get("/protected").status_code, 200)
        self.assertEqual(client.get("/protected").status_code, 429)

    def test_rate_limiting_resets_after_window_expires(self):
        app = _build_app(
            {
                "auth_enabled": False,
                "rate_limit_enabled": True,
                "rate_limit_rpm": 1,
            }
        )
        client = TestClient(app)

        self.assertEqual(client.get("/protected").status_code, 200)
        self.assertEqual(client.get("/protected").status_code, 429)

        # Wait for one minute window to expire.
        time.sleep(61)
        self.assertEqual(client.get("/protected").status_code, 200)

    def test_middleware_blocks_injection_input(self):
        client = TestClient(_build_app({"auth_enabled": False}))
        resp = client.get("/echo", params={"value": "'; DROP TABLE users"})
        self.assertEqual(resp.status_code, 400)

    def test_health_endpoint_bypasses_auth(self):
        client = TestClient(_build_app({"auth_enabled": True, "api_key": "secret"}))
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_classification_header_injected_on_all_responses(self):
        client = TestClient(_build_app({"auth_enabled": False}))
        resp = client.get("/protected")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("X-Classification", resp.headers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
