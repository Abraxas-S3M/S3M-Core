"""
S3M Governed Replication Engine
UNCLASSIFIED - FOUO

Implements security-hardened model replica governance for tactical deployments.
Replication is gated by cryptographic token validation and policy checks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


class ReplicationToken:
    """Signed authorization token for controlled replication actions."""

    def __init__(
        self,
        issuer: str,
        subject_node: str,
        max_replicas: int = 1,
        ttl_seconds: int = 3600,
    ):
        if not issuer:
            raise ValueError("issuer must be non-empty")
        if not subject_node:
            raise ValueError("subject_node must be non-empty")
        if max_replicas <= 0:
            raise ValueError("max_replicas must be > 0")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")

        now = _utcnow()
        self.token_id = str(uuid4())
        self.issuer = issuer
        self.subject_node = subject_node
        self.max_replicas = int(max_replicas)
        self.issued_at = _iso(now)
        self.expires_at = _iso(now + timedelta(seconds=int(ttl_seconds)))
        self.signature = ""

    def _payload(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "issuer": self.issuer,
            "subject_node": self.subject_node,
            "max_replicas": self.max_replicas,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def _compute_signature(payload: Dict[str, Any], secret_key: str) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hmac.new(secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

    def sign(self, secret_key: str) -> None:
        self.signature = self._compute_signature(self._payload(), secret_key)

    def to_dict(self) -> Dict[str, Any]:
        payload = self._payload()
        payload["signature"] = self.signature
        return payload

    @classmethod
    def verify(cls, token_data: Dict[str, Any], secret_key: str) -> bool:
        required = {
            "token_id",
            "issuer",
            "subject_node",
            "max_replicas",
            "issued_at",
            "expires_at",
            "signature",
        }
        if not isinstance(token_data, dict) or not required.issubset(token_data.keys()):
            return False

        try:
            expires_at = _parse_iso(str(token_data["expires_at"]))
            if expires_at <= _utcnow():
                return False
            payload = {
                "token_id": token_data["token_id"],
                "issuer": token_data["issuer"],
                "subject_node": token_data["subject_node"],
                "max_replicas": int(token_data["max_replicas"]),
                "issued_at": token_data["issued_at"],
                "expires_at": token_data["expires_at"],
            }
            expected = cls._compute_signature(payload, secret_key)
            return hmac.compare_digest(expected, str(token_data["signature"]))
        except Exception:
            return False


class ReplicationPolicy:
    """Policy gate for replication constraints in tactical environments."""

    _CLASS_RANK = {
        "UNCLASSIFIED": 0,
        "CONFIDENTIAL": 1,
        "SECRET": 2,
        "TOP_SECRET": 3,
    }

    def __init__(self, max_fleet: int = 32):
        if max_fleet <= 0:
            raise ValueError("max_fleet must be > 0")
        self._max_fleet = int(max_fleet)
        self._min_classification = "UNCLASSIFIED"
        self._allowed_subnets: List[str] = []

    def set_max_fleet(self, max_fleet: int) -> None:
        if max_fleet <= 0:
            raise ValueError("max_fleet must be > 0")
        self._max_fleet = int(max_fleet)

    def set_min_classification(self, level: str) -> None:
        key = str(level).upper()
        if key not in self._CLASS_RANK:
            raise ValueError("unsupported classification level")
        self._min_classification = key

    def set_allowed_subnets(self, prefixes: List[str]) -> None:
        self._allowed_subnets = [str(p) for p in prefixes if str(p)]

    def evaluate(
        self,
        current_fleet_size: int,
        target_classification: str = "UNCLASSIFIED",
        target_ip: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []

        if current_fleet_size >= self._max_fleet:
            violations.append(
                {
                    "rule": "fleet_size_limit",
                    "message": "Replication denied: maximum fleet size reached.",
                }
            )

        target_level = str(target_classification).upper()
        if target_level not in self._CLASS_RANK:
            violations.append(
                {
                    "rule": "classification_gate",
                    "message": "Replication denied: unknown target classification.",
                }
            )
        elif self._CLASS_RANK[target_level] < self._CLASS_RANK[self._min_classification]:
            violations.append(
                {
                    "rule": "classification_gate",
                    "message": "Replication denied: target classification below policy floor.",
                }
            )

        if self._allowed_subnets and target_ip is not None:
            if not any(str(target_ip).startswith(prefix) for prefix in self._allowed_subnets):
                violations.append(
                    {
                        "rule": "subnet_restriction",
                        "message": "Replication denied: target network not in allowed subnet list.",
                    }
                )

        return violations


class GovernedReplicationEngine:
    """Secure replication orchestrator with cryptographic and policy gates."""

    def __init__(self, secret_key: str, max_fleet: int = 32):
        if not secret_key:
            raise ValueError("secret_key must be non-empty")
        self._secret_key = secret_key
        self.policy = ReplicationPolicy(max_fleet=max_fleet)
        self._active: Dict[str, Dict[str, Any]] = {}
        self._quarantined: Dict[str, Dict[str, Any]] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def _audit(self, action: str, **details: Any) -> None:
        self._audit_log.append(
            {
                "action": action,
                "timestamp": _iso(_utcnow()),
                **details,
            }
        )

    @staticmethod
    def _validate_params(params: Dict[str, np.ndarray]) -> None:
        if not isinstance(params, dict) or not params:
            raise ValueError("params must be a non-empty dict of numpy arrays")
        for name, arr in params.items():
            if not isinstance(name, str) or not name:
                raise ValueError("parameter names must be non-empty strings")
            if not isinstance(arr, np.ndarray):
                raise ValueError("all parameter values must be numpy arrays")
            if not np.isfinite(arr).all():
                raise ValueError("parameters must contain only finite numeric values")

    def issue_token(
        self,
        issuer: str,
        subject_node: str,
        max_replicas: int = 1,
        ttl_seconds: int = 3600,
    ) -> Dict[str, Any]:
        token = ReplicationToken(
            issuer=issuer,
            subject_node=subject_node,
            max_replicas=max_replicas,
            ttl_seconds=ttl_seconds,
        )
        token.sign(self._secret_key)
        token_dict = token.to_dict()
        self._audit("token_issued", issuer=issuer, subject_node=subject_node, token_id=token.token_id)
        return token_dict

    def _authorize_admin(self, token: Dict[str, Any]) -> bool:
        if not ReplicationToken.verify(token, self._secret_key):
            return False
        return str(token.get("issuer", "")).lower() == "admin"

    def replicate(
        self,
        target_node: str,
        params: Dict[str, np.ndarray],
        token: Dict[str, Any],
        target_classification: str = "UNCLASSIFIED",
        target_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not ReplicationToken.verify(token, self._secret_key):
            self._audit("replication_denied", gate="crypto_auth", target_node=target_node)
            return {"error": "invalid_or_expired_token", "gate": "crypto_auth"}

        if str(token.get("subject_node")) != str(target_node):
            self._audit("replication_denied", gate="subject_mismatch", target_node=target_node)
            return {"error": "token_subject_mismatch", "gate": "subject"}

        subject_count = sum(1 for r in self._active.values() if r["target_node"] == target_node)
        if subject_count >= int(token.get("max_replicas", 1)):
            self._audit("replication_denied", gate="token_scope", target_node=target_node)
            return {"error": "token_replica_limit_exceeded", "gate": "token_scope"}

        violations = self.policy.evaluate(
            current_fleet_size=len(self._active),
            target_classification=target_classification,
            target_ip=target_ip,
        )
        if violations:
            self._audit("replication_denied", gate="policy", target_node=target_node, violations=violations)
            return {"error": "policy_violation", "gate": "policy", "violations": violations}

        self._validate_params(params)
        replica_id = str(uuid4())
        replica = {
            "replica_id": replica_id,
            "target_node": target_node,
            "created_at": _iso(_utcnow()),
            "status": "active",
            "param_shapes": {k: list(v.shape) for k, v in params.items()},
        }
        self._active[replica_id] = replica
        self._audit("replication_executed", replica_id=replica_id, target_node=target_node)
        return {"success": True, "replica": replica}

    def kill_replica(self, replica_id: str, token: Dict[str, Any]) -> Dict[str, Any]:
        if not self._authorize_admin(token):
            return {"error": "admin_authorization_required", "gate": "crypto_auth"}

        if replica_id in self._active:
            self._active.pop(replica_id, None)
            self._quarantined.pop(replica_id, None)
            self._audit("replica_killed", replica_id=replica_id)
            return {"success": True, "replica_id": replica_id}
        if replica_id in self._quarantined:
            self._quarantined.pop(replica_id, None)
            self._audit("replica_killed", replica_id=replica_id)
            return {"success": True, "replica_id": replica_id}
        return {"error": "replica_not_found", "replica_id": replica_id}

    def quarantine_replica(
        self,
        replica_id: str,
        token: Dict[str, Any],
        reason: str = "policy_review",
    ) -> Dict[str, Any]:
        if not self._authorize_admin(token):
            return {"error": "admin_authorization_required", "gate": "crypto_auth"}
        if replica_id not in self._active:
            return {"error": "replica_not_found", "replica_id": replica_id}

        replica = self._active.pop(replica_id)
        replica["status"] = "quarantined"
        replica["quarantine_reason"] = reason
        replica["quarantined_at"] = _iso(_utcnow())
        self._quarantined[replica_id] = replica
        self._audit("replica_quarantined", replica_id=replica_id, reason=reason)
        return {"success": True, "replica": replica}

    def list_active(self) -> List[Dict[str, Any]]:
        return list(self._active.values())

    def list_quarantined(self) -> List[Dict[str, Any]]:
        return list(self._quarantined.values())

    def health_check(self) -> Dict[str, Any]:
        return {
            "active_replicas": len(self._active),
            "quarantined_replicas": len(self._quarantined),
            "audit_events": len(self._audit_log),
        }
