#!/usr/bin/env python3
"""Tests for S3M API Server - Phase 4."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from fastapi.testclient import TestClient
from src.api.server import app


class TestHealthEndpoint(unittest.TestCase):
    """Test /health endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_has_required_fields(self):
        resp = self.client.get("/health")
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("engines", data)
        self.assertIn("uptime_seconds", data)
        self.assertEqual(data["status"], "operational")

    def test_health_shows_four_engines(self):
        resp = self.client.get("/health")
        engines = resp.json()["engines"]
        self.assertEqual(len(engines), 4)
        for name in ["phi3", "grok", "mistral", "allam"]:
            self.assertIn(name, engines)


class TestInferenceEndpoint(unittest.TestCase):
    """Test /inference endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    def test_inference_returns_200(self):
        resp = self.client.post("/inference", json={
            "prompt": "What is the tactical situation?",
            "engine": "phi3"
        })
        self.assertEqual(resp.status_code, 200)

    def test_inference_has_response_fields(self):
        resp = self.client.post("/inference", json={
            "prompt": "Analyze the threat",
            "engine": "grok"
        })
        data = resp.json()
        self.assertIn("request_id", data)
        self.assertIn("engine", data)
        self.assertIn("response", data)
        self.assertIn("tokens_used", data)
        self.assertIn("latency_ms", data)

    def test_inference_respects_engine_choice(self):
        resp = self.client.post("/inference", json={
            "prompt": "Test prompt",
            "engine": "mistral"
        })
        self.assertEqual(resp.json()["engine"], "mistral")

    def test_inference_domain_routing(self):
        resp = self.client.post("/inference", json={
            "prompt": "Supply chain status",
            "domain": "logistics"
        })
        self.assertEqual(resp.json()["engine"], "mistral")

    def test_inference_empty_prompt_rejected(self):
        resp = self.client.post("/inference", json={
            "prompt": ""
        })
        self.assertEqual(resp.status_code, 422)


class TestConsensusEndpoint(unittest.TestCase):
    """Test /consensus endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    def test_consensus_returns_200(self):
        resp = self.client.post("/consensus", json={
            "prompt": "Assess current situation"
        })
        self.assertEqual(resp.status_code, 200)

    def test_consensus_has_all_engines(self):
        resp = self.client.post("/consensus", json={
            "prompt": "Threat assessment"
        })
        data = resp.json()
        self.assertIn("engine_responses", data)
        self.assertIn("agreement_score", data)
        self.assertEqual(len(data["engine_responses"]), 4)

    def test_consensus_subset_engines(self):
        resp = self.client.post("/consensus", json={
            "prompt": "Quick analysis",
            "engines": ["phi3", "grok"]
        })
        data = resp.json()
        self.assertEqual(len(data["engine_responses"]), 2)

    def test_consensus_invalid_engine(self):
        resp = self.client.post("/consensus", json={
            "prompt": "Test",
            "engines": ["phi3", "invalid_engine"]
        })
        self.assertEqual(resp.status_code, 400)


class TestDomainInference(unittest.TestCase):
    """Test /inference/{domain} endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    def test_tactical_domain(self):
        resp = self.client.post("/inference/tactical", json={
            "prompt": "Forward operating base status"
        })
        self.assertEqual(resp.status_code, 200)

    def test_invalid_domain(self):
        resp = self.client.post("/inference/nonexistent", json={
            "prompt": "Test"
        })
        self.assertEqual(resp.status_code, 404)


class TestEngineManagement(unittest.TestCase):
    """Test engine management endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_list_engines(self):
        resp = self.client.get("/engines")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 4)

    def test_engine_detail(self):
        resp = self.client.get("/engines/phi3")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "phi3")

    def test_unknown_engine_detail(self):
        resp = self.client.get("/engines/unknown")
        self.assertEqual(resp.status_code, 404)

    def test_load_engine(self):
        resp = self.client.post("/engines/phi3/load")
        self.assertEqual(resp.status_code, 200)

    def test_unload_engine(self):
        resp = self.client.post("/engines/phi3/unload")
        self.assertEqual(resp.status_code, 200)

    def test_update_engine_config(self):
        resp = self.client.patch("/engines/phi3", json={
            "gpu_layers": 40,
            "temperature": 0.5
        })
        self.assertEqual(resp.status_code, 200)


class TestRoutingEndpoints(unittest.TestCase):
    """Test routing endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_get_routing(self):
        resp = self.client.get("/routing")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("domain_routing", resp.json())

    def test_update_routing(self):
        resp = self.client.put("/routing", json={
            "tactical": "grok"
        })
        self.assertEqual(resp.status_code, 200)


class TestAuditAndStats(unittest.TestCase):
    """Test audit and stats endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_audit_log(self):
        # Generate some activity first
        self.client.post("/inference", json={"prompt": "Test for audit"})
        resp = self.client.get("/audit")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("logs", resp.json())

    def test_audit_with_limit(self):
        resp = self.client.get("/audit?limit=5")
        self.assertEqual(resp.status_code, 200)

    def test_stats(self):
        resp = self.client.get("/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_requests", data)
        self.assertIn("engines_loaded", data)


if __name__ == "__main__":
    print("=" * 60)
    print("  S3M Phase 4 API Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
