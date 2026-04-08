"""Contract tests for the GUI Bridge API layer.

These tests validate that every endpoint returns the exact JSON shape
the S3M-GUI frontend expects. Run with: pytest tests/test_gui_bridge.py -v
"""

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)
BASE = "/api/v1"


class TestCommandWorkspace:
    def test_operational_context_shape(self):
        r = client.get(f"{BASE}/workspaces/command/operational-context")
        assert r.status_code == 200
        data = r.json()
        assert "threats" in data
        assert "decisions" in data
        assert "directives" in data
        assert "updatedAt" in data
        if data["threats"]:
            t = data["threats"][0]
            assert all(
                k in t
                for k in ("id", "label", "level", "domain", "summary", "updatedAt")
            )
        if data["decisions"]:
            d = data["decisions"][0]
            assert all(
                k in d
                for k in (
                    "id",
                    "title",
                    "risk",
                    "confidence",
                    "description",
                    "status",
                    "severity",
                )
            )

    def test_timeline_events_shape(self):
        r = client.get(f"{BASE}/workspaces/command/timeline-events")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "updatedAt" in data


class TestCOPWorkspace:
    def test_tracks_shape(self):
        r = client.get(f"{BASE}/workspaces/cop/tracks")
        assert r.status_code == 200
        data = r.json()
        assert "tracks" in data
        assert "updatedAt" in data

    def test_threat_tracks_shape(self):
        r = client.get(f"{BASE}/workspaces/cop/threat-tracks")
        assert r.status_code == 200
        data = r.json()
        assert "tracks" in data


class TestDecisionsWorkspace:
    def test_queue_shape(self):
        r = client.get(f"{BASE}/workspaces/decisions/queue")
        assert r.status_code == 200
        data = r.json()
        assert "decisions" in data
        assert "queueCounts" in data
        counts = data["queueCounts"]
        assert all(
            k in counts
            for k in ("pending", "autoApproved", "humanApproved", "vetoed", "stale")
        )

    def test_approve_returns_200(self):
        r = client.post(
            f"{BASE}/workspaces/decisions/queue/R001/approve", json={"comment": "test"}
        )
        assert r.status_code == 200

    def test_reject_returns_200(self):
        r = client.post(
            f"{BASE}/workspaces/decisions/queue/R002/reject", json={"comment": "test"}
        )
        assert r.status_code == 200


class TestRiskWorkspace:
    def test_metrics_shape(self):
        r = client.get(f"{BASE}/workspaces/risk/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "composite" in data
        assert "domains" in data
        assert "forecast" in data
        assert "drivers" in data
        assert isinstance(data["composite"], int)
        assert 0 <= data["composite"] <= 100


class TestReadinessWorkspace:
    def test_summary_shape(self):
        r = client.get(f"{BASE}/workspaces/readiness/summary")
        assert r.status_code == 200
        data = r.json()
        assert "personnel" in data
        assert "equipment" in data
        assert "unitStatus" in data
        p = data["personnel"]
        assert all(k in p for k in ("available", "deployed", "onLeave"))

    def test_enriched_shape(self):
        r = client.get(f"{BASE}/workspaces/readiness/enriched")
        assert r.status_code == 200
        data = r.json()
        assert "personnel" in data
        assert "equipment" in data
        assert "unitStatus" in data
        assert "certifications" in data
        assert "qualificationMatrix" in data
        assert "readinessForecast" in data
        assert "updatedAt" in data
        if data["certifications"]:
            cert = data["certifications"][0]
            assert all(
                k in cert
                for k in (
                    "certType",
                    "nameEn",
                    "nameAr",
                    "total",
                    "current",
                    "expiringSoon",
                    "expired",
                )
            )


class TestSurveillanceWorkspace:
    def test_assets_shape(self):
        r = client.get(f"{BASE}/workspaces/surveillance/assets")
        assert r.status_code == 200
        data = r.json()
        assert "assets" in data
        assert "taskingQueue" in data
        assert "targetBoard" in data

    def test_collection_shape(self):
        r = client.get(f"{BASE}/workspaces/surveillance/collection")
        assert r.status_code == 200
        data = r.json()
        assert "collection" in data
        assert "updatedAt" in data

    def test_source_reliability_shape(self):
        r = client.get(f"{BASE}/workspaces/surveillance/source-reliability")
        assert r.status_code == 200
        data = r.json()
        assert "sources" in data
        assert "updatedAt" in data
        assert isinstance(data["sources"], list)

    def test_fusion_brief_shape(self):
        r = client.get(f"{BASE}/workspaces/surveillance/fusion-brief")
        assert r.status_code == 200
        data = r.json()
        assert "brief" in data
        assert "updatedAt" in data

    def test_watchlists_shape(self):
        r = client.get(f"{BASE}/workspaces/surveillance/watchlists")
        assert r.status_code == 200
        data = r.json()
        assert "watchlists" in data
        assert "updatedAt" in data
        watchlists = data["watchlists"]
        assert all(
            key in watchlists
            for key in ("persons", "organizations", "vessels", "vehicles", "sites")
        )


class TestCommsWorkspace:
    def test_messages_shape(self):
        r = client.get(f"{BASE}/workspaces/communication/messages")
        assert r.status_code == 200
        data = r.json()
        assert "inbox" in data
        if data["inbox"]:
            msg = data["inbox"][0]
            assert all(k in msg for k in ("id", "from", "to", "subject", "body"))


class TestCyberWorkspace:
    def test_incidents_shape(self):
        r = client.get(f"{BASE}/workspaces/cyber/incidents")
        assert r.status_code == 200
        data = r.json()
        assert "incidents" in data

    def test_resilience_shape(self):
        r = client.get(f"{BASE}/workspaces/cyber/resilience")
        assert r.status_code == 200
        data = r.json()
        assert "resilience" in data


class TestSimulationWorkspace:
    def test_scenarios_shape(self):
        r = client.get(f"{BASE}/workspaces/simulation/scenarios")
        assert r.status_code == 200
        data = r.json()
        assert "scenarios" in data

    def test_catalog_shape(self):
        r = client.get(f"{BASE}/workspaces/simulation/catalog")
        assert r.status_code == 200
        data = r.json()
        assert "scenarios" in data
        assert "updatedAt" in data

    def test_aar_shape(self):
        r = client.get(f"{BASE}/workspaces/simulation/aar/SCN-001")
        assert r.status_code == 200
        data = r.json()
        assert data["scenarioId"] == "SCN-001"
        assert "aar" in data
        assert "updatedAt" in data

    def test_compare_shape(self):
        r = client.post(f"{BASE}/workspaces/simulation/compare/SCN-001")
        assert r.status_code == 200
        data = r.json()
        assert "comparison" in data
        assert "updatedAt" in data


class TestSustainmentWorkspace:
    def test_fleet_shape(self):
        r = client.get(f"{BASE}/workspaces/sustainment/fleet")
        assert r.status_code == 200
        data = r.json()
        assert "units" in data

    def test_supply_shape(self):
        r = client.get(f"{BASE}/workspaces/sustainment/supply")
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data


class TestPlanningWorkspace:
    def test_phases_shape(self):
        r = client.get(f"{BASE}/workspaces/planning/phases")
        assert r.status_code == 200
        data = r.json()
        assert "phases" in data

    def test_coas_shape(self):
        r = client.get(f"{BASE}/workspaces/planning/coas")
        assert r.status_code == 200
        data = r.json()
        assert "coursesOfAction" in data

    def test_replan_triggers_shape(self):
        r = client.get(f"{BASE}/workspaces/planning/replan-triggers")
        assert r.status_code == 200
        data = r.json()
        assert "triggers" in data
        assert "updatedAt" in data

    def test_suggestions_shape(self):
        r = client.post(
            f"{BASE}/workspaces/planning/suggestions",
            json={"plan_context": "Enemy armored column observed near crossing sector."},
        )
        assert r.status_code == 200
        data = r.json()
        assert "suggestions" in data
        assert "updatedAt" in data


class TestAuth:
    def test_login_success(self):
        r = client.post(
            f"{BASE}/auth/login",
            json={"username": "commander", "password": "s3m-cmd-2026"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "commander"

    def test_login_failure(self):
        r = client.post(
            f"{BASE}/auth/login", json={"username": "bad", "password": "bad"}
        )
        assert r.status_code == 401

    def test_me_with_token(self):
        login = client.post(
            f"{BASE}/auth/login",
            json={"username": "analyst", "password": "s3m-analyst-2026"},
        )
        token = login.json()["token"]
        r = client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["role"] == "analyst"


class TestAIChat:
    def test_chat_english(self):
        r = client.post(
            f"{BASE}/ai/chat",
            json={"prompt": "What is the current threat level?", "language": "EN"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        assert "engine" in data

    def test_chat_arabic(self):
        r = client.post(
            f"{BASE}/ai/chat",
            json={"prompt": "ما هو مستوى التهديد؟", "language": "AR"},
        )
        assert r.status_code == 200
        assert r.json()["engine"] == "allam"
