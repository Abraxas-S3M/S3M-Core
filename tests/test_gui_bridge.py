"""Contract tests for the GUI Bridge API layer.

These tests validate that every endpoint returns the exact JSON shape
the S3M-GUI frontend expects. Run with: pytest tests/test_gui_bridge.py -v
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

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

    def test_agents_shape(self):
        r = client.get(f"{BASE}/workspaces/command/agents")
        assert r.status_code == 200
        data = r.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)
        if data["agents"]:
            agent = data["agents"][0]
            assert all(
                k in agent
                for k in ("id", "name", "role", "status", "health", "function")
            )

    def test_agent_detail_shape(self):
        list_resp = client.get(f"{BASE}/workspaces/command/agents")
        assert list_resp.status_code == 200
        agents = list_resp.json().get("agents", [])
        assert agents
        agent_id = agents[0]["id"]
        detail_resp = client.get(f"{BASE}/workspaces/command/agents/{agent_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert "agent" in detail
        assert "logs" in detail

    def test_program_agent_returns_status(self):
        list_resp = client.get(f"{BASE}/workspaces/command/agents")
        assert list_resp.status_code == 200
        agents = list_resp.json().get("agents", [])
        assert agents
        agent_id = agents[0]["id"]
        r = client.post(
            f"{BASE}/workspaces/command/agents/{agent_id}/program",
            json={
                "agentId": agent_id,
                "instructions": "Hold pattern over route alpha.",
                "language": "EN",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "accepted"
        assert data["agentId"] == agent_id


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

    def test_replay_shape(self):
        r = client.get(
            f"{BASE}/workspaces/cop/replay",
            params={
                "start_time": "2026-01-01T00:00:00+00:00",
                "end_time": "2026-12-31T23:59:59+00:00",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            frame = data[0]
            assert "timestamp" in frame
            assert "tracks" in frame

    def test_mission_layer_shape(self):
        r = client.get(f"{BASE}/workspaces/cop/mission-layer")
        assert r.status_code == 200
        data = r.json()
        assert "missionId" in data
        assert "waypoints" in data
        assert "phaseLines" in data
        assert "objectives" in data


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

    def test_explanation_shape(self):
        r = client.get(f"{BASE}/workspaces/decisions/queue/R001/explain")
        assert r.status_code == 200
        data = r.json()
        assert all(
            key in data
            for key in (
                "decisionId",
                "evidence",
                "confidenceBreakdown",
                "dissentingViews",
                "doctrineChecks",
                "expectedUpside",
                "expectedDownside",
                "updatedAt",
            )
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

    def test_what_if_shape(self):
        scenario = {"threat": "high", "readiness": "low"}
        r = client.post(f"{BASE}/workspaces/risk/what-if", json=scenario)
        assert r.status_code == 200
        data = r.json()
        assert "scenario" in data
        assert "result" in data
        assert "updatedAt" in data
        assert data["scenario"] == scenario


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

    def test_bearer_health_shape(self):
        r = client.get(f"{BASE}/workspaces/communication/bearer-health")
        assert r.status_code == 200
        data = r.json()
        assert "bearers" in data
        assert "updatedAt" in data
        if data["bearers"]:
            bearer = data["bearers"][0]
            assert all(k in bearer for k in ("type", "status", "signal", "latency"))

    def test_degradation_advice_shape(self):
        r = client.post(
            f"{BASE}/workspaces/communication/degradation-advice",
            json={"bearers": [{"type": "HF", "status": "degraded"}]},
        )
        assert r.status_code == 200
        data = r.json()
        assert "advice" in data
        assert "updatedAt" in data


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

    def test_model_security_shape(self):
        r = client.get(f"{BASE}/workspaces/cyber/model-security")
        assert r.status_code == 200
        data = r.json()
        assert "modelSecurity" in data
        assert "updatedAt" in data

    def test_trust_fabric_shape(self):
        r = client.get(f"{BASE}/workspaces/cyber/trust-fabric")
        assert r.status_code == 200
        data = r.json()
        assert "crypto" in data
        assert "zeroKnowledge" in data
        assert "updatedAt" in data

    def test_attack_capabilities_shape(self):
        r = client.get(f"{BASE}/workspaces/cyber/attack-capabilities")
        assert r.status_code == 200
        data = r.json()
        assert "capabilities" in data
        assert "updatedAt" in data

    def test_attack_plan_shape(self):
        r = client.post(
            f"{BASE}/workspaces/cyber/attack/plan",
            json={
                "adversaryId": "sim-red-team-phishing",
                "targets": ["edge-node-1"],
                "approvalToken": "approved-by-ops",
                "objective": "Test",
                "parameters": {},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "operationId" in data
        assert "plan" in data
        assert "updatedAt" in data

    def test_attack_status_shape(self):
        planned = client.post(
            f"{BASE}/workspaces/cyber/attack/plan",
            json={
                "adversaryId": "sim-red-team-lateral",
                "targets": ["edge-node-2"],
                "approvalToken": "approved-by-ops",
                "objective": "Status test",
                "parameters": {},
            },
        )
        assert planned.status_code == 200
        operation_id = planned.json().get("operationId")
        assert operation_id

        r = client.get(f"{BASE}/workspaces/cyber/attack/{operation_id}/status")
        assert r.status_code == 200
        data = r.json()
        assert "operationId" in data
        assert "status" in data
        assert "steps_completed" in data["status"]
        assert "techniques_used" in data["status"]
        assert "updatedAt" in data

    def test_attack_execute_shape(self):
        r = client.post(
            f"{BASE}/workspaces/cyber/attack/execute",
            json={"playbookId": "", "objective": "Test", "parameters": {}},
        )
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "execution" in data
        assert "updatedAt" in data


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

    def test_maintenance_predictions_shape(self):
        r = client.get(f"{BASE}/workspaces/sustainment/maintenance/predictions")
        assert r.status_code == 200
        data = r.json()
        assert "predictions" in data
        assert "updatedAt" in data

    def test_supply_twin_shape(self):
        r = client.get(f"{BASE}/workspaces/sustainment/supply-twin")
        assert r.status_code == 200
        data = r.json()
        assert "supplyChain" in data
        assert "updatedAt" in data


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


class TestSystemStatus:
    def test_system_status_shape(self):
        r = client.get(f"{BASE}/system/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "operational"
        assert "engines" in data
        assert isinstance(data["engines"], dict)
        assert "uptime" in data
        assert isinstance(data["uptime"], int)
        assert data["uptime"] >= 0
        assert data["version"] == "0.2.0"
        assert "updatedAt" in data
        datetime.fromisoformat(data["updatedAt"])


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
