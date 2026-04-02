"""Unit tests for governed replication security controls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from src.edge_compute.governed_replication import (
    GovernedReplicationEngine,
    ReplicationPolicy,
    ReplicationToken,
)
from src.security.crypto.secure_audit_log import SecureAuditLog


def _parent_params() -> dict[str, np.ndarray]:
    return {"w": np.ones((16,), dtype=np.float32)}


def test_replication_token_sign_and_verify():
    token = ReplicationToken(
        issuer="hq",
        subject="node-alpha",
        max_replicas=2,
        classification="secret",
        ttl_seconds=120,
    )
    token.sign("test-secret")
    token_dict = token.to_dict()
    assert ReplicationToken.verify(token_dict, "test-secret")
    assert not ReplicationToken.verify(token_dict, "wrong-secret")


def test_replication_token_expired_rejected():
    token = ReplicationToken(
        issuer="hq",
        subject="node-alpha",
        max_replicas=1,
        classification="UNCLASSIFIED",
        ttl_seconds=60,
    )
    token.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    token.sign("test-secret")
    assert not ReplicationToken.verify(token.to_dict(), "test-secret")


def test_replication_policy_subnet_and_custom_rule_enforcement():
    policy = ReplicationPolicy(
        rules=[
            {
                "name": "deny-odd-fleet",
                "check": lambda current_fleet_size, *_: (
                    current_fleet_size % 2 == 0,
                    "fleet size must be even",
                ),
            }
        ]
    )
    policy.set_allowed_subnets(["10.0.0.0/24"])
    violations = policy.evaluate(
        current_fleet_size=1,
        target_classification="UNCLASSIFIED",
        target_ip="192.168.1.9",
        token={"max_replicas": 10},
    )
    rules = {item["rule"] for item in violations}
    assert "subnet_restriction" in rules
    assert "deny-odd-fleet" in rules


def test_governed_replication_happy_path_with_classification_inheritance():
    engine = GovernedReplicationEngine(secret_key="k", max_fleet=4, min_classification="UNCLASSIFIED")
    token = engine.issue_token(
        issuer="hq",
        subject="node-alpha",
        max_replicas=2,
        classification="SECRET",
        ttl_seconds=300,
    )
    result = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="TOP_SECRET",
        target_ip="10.0.0.12",
        target_memory_mb=256,
    )
    assert result["success"] is True
    replica = result["replica"]
    # Tactical sovereignty rule: child inherits parent classification.
    assert replica["classification"] == "SECRET"


def test_governed_replication_denied_on_subject_mismatch():
    engine = GovernedReplicationEngine(secret_key="k")
    token = engine.issue_token(issuer="hq", subject="node-alpha", classification="UNCLASSIFIED")
    result = engine.replicate(
        parent_node_id="node-bravo",
        parent_params=_parent_params(),
        token=token,
        target_classification="UNCLASSIFIED",
    )
    assert result["gate"] == "crypto_auth"
    assert "error" in result


def test_governed_replication_denied_on_data_sovereignty_downgrade():
    engine = GovernedReplicationEngine(secret_key="k")
    token = engine.issue_token(issuer="hq", subject="node-alpha", classification="SECRET")
    result = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="FOUO",
        target_ip="10.0.0.50",
    )
    assert result["gate"] == "policy"
    assert "lower than parent classification" in result["error"]


def test_governed_replication_denied_when_token_max_replicas_reached():
    engine = GovernedReplicationEngine(secret_key="k", max_fleet=10)
    token = engine.issue_token(
        issuer="hq",
        subject="node-alpha",
        max_replicas=1,
        classification="UNCLASSIFIED",
    )
    first = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="UNCLASSIFIED",
        target_memory_mb=64,
    )
    second = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="UNCLASSIFIED",
        target_memory_mb=64,
    )
    assert first["success"] is True
    assert second["gate"] == "policy"
    assert second["error"] == "policy violations"


def test_governed_replication_denied_on_resource_budget():
    engine = GovernedReplicationEngine(secret_key="k", max_total_memory_mb=100)
    token = engine.issue_token(issuer="hq", subject="node-alpha", max_replicas=3, classification="UNCLASSIFIED")
    first = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="UNCLASSIFIED",
        target_memory_mb=60,
    )
    second = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="UNCLASSIFIED",
        target_memory_mb=50,
    )
    assert first["success"] is True
    assert second["gate"] == "resource"
    assert second["error"] == "resource budget exceeded"


def test_kill_and_quarantine_require_authenticated_token():
    engine = GovernedReplicationEngine(secret_key="k")
    good = engine.issue_token(issuer="hq", subject="node-alpha", max_replicas=2, classification="UNCLASSIFIED")
    bad = dict(good)
    bad["signature"] = "tampered"

    created = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=good,
        target_classification="UNCLASSIFIED",
    )
    replica_id = created["replica"]["replica_id"]

    denied = engine.quarantine_replica(replica_id, bad, reason="integrity alert")
    assert denied["error"] == "invalid authorization token"

    quarantined = engine.quarantine_replica(replica_id, good, reason="telemetry anomaly")
    assert quarantined["success"] is True

    second_created = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=good,
        target_classification="UNCLASSIFIED",
    )
    second_id = second_created["replica"]["replica_id"]
    killed = engine.kill_replica(second_id, good)
    assert killed["action"] == "killed"


def test_governed_replication_audits_to_secure_hash_chain(tmp_path):
    audit_log = SecureAuditLog(log_dir=str(tmp_path / "audit"))
    engine = GovernedReplicationEngine(secret_key="k")
    engine.set_audit_callback(audit_log.log)

    token = engine.issue_token(
        issuer="hq",
        subject="node-alpha",
        max_replicas=1,
        classification="UNCLASSIFIED",
    )
    replicate_result = engine.replicate(
        parent_node_id="node-alpha",
        parent_params=_parent_params(),
        token=token,
        target_classification="UNCLASSIFIED",
    )
    replica_id = replicate_result["replica"]["replica_id"]
    engine.kill_replica(replica_id, token)

    entries = audit_log.query(source="governed_replication", limit=20)
    actions = {entry["action"] for entry in entries}
    assert "token_issued" in actions
    assert "replication_executed" in actions
    assert "replica_killed" in actions
    assert audit_log.verify_chain()["valid"] is True
