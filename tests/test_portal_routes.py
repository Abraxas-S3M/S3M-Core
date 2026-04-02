#!/usr/bin/env python3
"""Unit tests for role-based portal API routes."""

import unittest

from fastapi.testclient import TestClient

from src.api.server import app
from src.api.portal_routes import UserRole, issue_token


class TestPortalRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @staticmethod
    def _auth_header(user_id: str, role: UserRole) -> dict[str, str]:
        token = issue_token(user_id=user_id, role=role)
        return {"Authorization": f"Bearer {token}"}

    def test_auth_token_issue(self) -> None:
        resp = self.client.post("/portal/auth/token", params={"user_id": "u1", "role": "COMMANDER"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("token", payload)
        self.assertEqual(payload["role"], "COMMANDER")

    def test_auth_token_rejects_empty_user(self) -> None:
        resp = self.client.post("/portal/auth/token", params={"user_id": "   ", "role": "COMMANDER"})
        self.assertEqual(resp.status_code, 400)

    def test_commander_dashboard_requires_auth(self) -> None:
        resp = self.client.get("/portal/commander/dashboard")
        self.assertEqual(resp.status_code, 401)

    def test_commander_dashboard_permissions_and_i18n(self) -> None:
        headers = self._auth_header("cmd-1", UserRole.COMMANDER)
        headers["X-Lang"] = "en"
        resp = self.client.get("/portal/commander/dashboard", headers=headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["lang"], "en")
        self.assertEqual(body["labels"]["cop_title"], "Common Operating Picture")
        self.assertEqual(body["role"], "COMMANDER")

    def test_analyst_can_read_intel(self) -> None:
        headers = self._auth_header("ana-1", UserRole.ANALYST)
        resp = self.client.get("/portal/analyst/intel", headers=headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["role"], "ANALYST")
        self.assertIsInstance(body["threats"], list)
        self.assertIsInstance(body["assets"], list)

    def test_maintainer_assets_permission(self) -> None:
        bad_headers = self._auth_header("ana-2", UserRole.ANALYST)
        bad_resp = self.client.get("/portal/maintainer/assets", headers=bad_headers)
        self.assertEqual(bad_resp.status_code, 403)

        ok_headers = self._auth_header("mnt-1", UserRole.MAINTAINER)
        ok_resp = self.client.get("/portal/maintainer/assets", headers=ok_headers)
        self.assertEqual(ok_resp.status_code, 200)
        self.assertIn("alerts", ok_resp.json())

    def test_operator_approve_requires_correct_permission(self) -> None:
        operator_headers = self._auth_header("op-1", UserRole.OPERATOR)
        denied = self.client.post(
            "/portal/operator/approve",
            params={"ticket_id": "APR-77", "granted": "true"},
            headers=operator_headers,
        )
        self.assertEqual(denied.status_code, 403)

        commander_headers = self._auth_header("cmd-2", UserRole.COMMANDER)
        ok = self.client.post(
            "/portal/operator/approve",
            params={"ticket_id": "APR-77", "granted": "true"},
            headers=commander_headers,
        )
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        self.assertIn("ticket", body)
        self.assertIn("signature", body)
        self.assertEqual(body["signature"]["action"], "APPROVAL")

    def test_invalid_token_rejected(self) -> None:
        headers = {"Authorization": "Bearer not-a-valid-token"}
        resp = self.client.get("/portal/commander/dashboard", headers=headers)
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
