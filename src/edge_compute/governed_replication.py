"""
S3M Governed Self-Replication
UNCLASSIFIED - FOUO

Security-hardened replication layer that wraps replication actions with
military-grade controls required for classified tactical deployments.

Every replication action must pass through a multi-gate pipeline:
  1) Crypto Auth (HMAC token verification)
  2) Policy Check (classification, subnet, time window, custom rules)
  3) Resource Gate (fleet memory budget)
  4) Replicate & Audit (immutable event callback integration)

This module is designed for offline operation on edge hardware and uses only
standard-library cryptography primitives.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import numpy as np

logger = logging.getLogger("s3m.edge.governed_replication")


# Classification hierarchy (higher index = more restricted)
CLASSIFICATION_LEVELS = {
    "UNCLASSIFIED": 0,
    "FOUO": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
    "TOP_SECRET": 4,
}


def _normalize_classification(level: str) -> str:
    if not isinstance(level, str) or not level.strip():
        raise ValueError("classification must be a non-empty string")
    normalized = level.strip().upper()
    if normalized not in CLASSIFICATION_LEVELS:
        raise ValueError(f"unsupported classification level: {level}")
    return normalized


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class ReplicationToken:
    """
    HMAC-SHA256 signed authorization token for replication actions.

    Token fields:
      - token_id: unique identifier
      - issuer: central authority node ID
      - subject: node ID authorized to replicate
      - max_replicas: upper bound authorized by this token
      - classification: minimum classification authorized by issuer
      - issued_at: UTC ISO-8601 timestamp
      - expires_at: UTC ISO-8601 timestamp
      - signature: HMAC-SHA256(payload)
    """

    _PAYLOAD_FIELDS = (
        "token_id",
        "issuer",
        "subject",
        "max_replicas",
        "classification",
        "issued_at",
        "expires_at",
    )

    def __init__(
        self,
        issuer: str,
        subject: Optional[str] = None,
        max_replicas: int = 1,
        classification: str = "UNCLASSIFIED",
        ttl_seconds: int = 3600,
        subject_node: Optional[str] = None,
    ) -> None:
        # Backward compatibility: support both subject and subject_node.
        resolved_subject = subject if subject is not None else subject_node

        if not _is_non_empty_string(issuer):
            raise ValueError("issuer must be a non-empty string")
        if not _is_non_empty_string(resolved_subject):
            raise ValueError("subject must be a non-empty string")
        if not isinstance(max_replicas, int) or max_replicas <= 0:
            raise ValueError("max_replicas must be a positive integer")
        if not isinstance(ttl_seconds, int) or ttl_seconds < 0:
            raise ValueError("ttl_seconds must be a non-negative integer")

        now = datetime.now(timezone.utc)
        self.token_id = str(uuid4())
        self.issuer = issuer.strip()
        self.subject = str(resolved_subject).strip()
        self.max_replicas = int(max_replicas)
        self.classification = _normalize_classification(classification)
        self.issued_at = now.isoformat()
        self.expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        self.signature = ""

    @property
    def subject_node(self) -> str:
        """Compatibility alias for older callers."""
        return self.subject

    def payload(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "issuer": self.issuer,
            "subject": self.subject,
            "max_replicas": self.max_replicas,
            "classification": self.classification,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def _canonical_payload_bytes(payload: Dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _payload_from_token_dict(token_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Accept old token shape with subject_node and no classification.
        if not isinstance(token_dict, dict):
            return None
        try:
            subject_value = token_dict.get("subject", token_dict.get("subject_node"))
            classification = token_dict.get("classification", "UNCLASSIFIED")
            return {
                "token_id": token_dict["token_id"],
                "issuer": token_dict["issuer"],
                "subject": subject_value,
                "max_replicas": int(token_dict["max_replicas"]),
                "classification": _normalize_classification(classification),
                "issued_at": token_dict["issued_at"],
                "expires_at": token_dict["expires_at"],
            }
        except Exception:
            return None

    def sign(self, secret_key: str) -> str:
        """Sign token payload with HMAC-SHA256."""
        if not _is_non_empty_string(secret_key):
            raise ValueError("secret_key must be a non-empty string")
        self.signature = hmac.new(
            secret_key.encode("utf-8"),
            self._canonical_payload_bytes(self.payload()),
            hashlib.sha256,
        ).hexdigest()
        return self.signature

    def to_dict(self) -> Dict[str, Any]:
        token = {**self.payload(), "signature": self.signature}
        # Include compatibility field expected by older callers.
        token["subject_node"] = token["subject"]
        return token

    @classmethod
    def verify(
        cls,
        token_dict: Dict[str, Any],
        secret_key: str,
        required_subject: Optional[str] = None,
    ) -> bool:
        """Verify token signature, field integrity, and expiry."""
        if not isinstance(token_dict, dict) or not _is_non_empty_string(secret_key):
            return False
        if not _is_non_empty_string(token_dict.get("signature")):
            return False

        payload = cls._payload_from_token_dict(token_dict)
        if payload is None:
            return False

        try:
            if not isinstance(payload["max_replicas"], int) or payload["max_replicas"] <= 0:
                return False
            if not _is_non_empty_string(payload["issuer"]) or not _is_non_empty_string(payload["subject"]):
                return False
            issued_at = datetime.fromisoformat(payload["issued_at"])
            expires_at = datetime.fromisoformat(payload["expires_at"])
            if issued_at.tzinfo is None or expires_at.tzinfo is None:
                return False
            if expires_at <= issued_at:
                return False
        except (TypeError, ValueError):
            return False

        expected = hmac.new(
            secret_key.encode("utf-8"),
            cls._canonical_payload_bytes(payload),
            hashlib.sha256,
        ).hexdigest()
        signature = str(token_dict.get("signature", ""))
        if not hmac.compare_digest(signature, expected):
            return False

        now = datetime.now(timezone.utc)
        if now > expires_at:
            return False

        if required_subject is not None and payload.get("subject") != required_subject:
            return False

        return True


class ReplicationPolicy:
    """
    Policy-as-code rules evaluated before tactical replication.

    Built-in controls:
      - classification floor gate
      - fleet size cap (optionally tightened by token max_replicas)
      - subnet allow-list using CIDR networks and prefix compatibility mode
      - UTC time window control
      - custom callable rules (fail-closed on exceptions)
    """

    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None, max_fleet: Optional[int] = None) -> None:
        self._rules: List[Dict[str, Any]] = rules or []
        self._default_max_fleet = 16
        self._allowed_subnets: List[ipaddress._BaseNetwork] = []
        self._allowed_prefixes: List[str] = []
        self._min_classification = "UNCLASSIFIED"
        self._time_window: Optional[Dict[str, int]] = None
        if max_fleet is not None:
            self.set_max_fleet(max_fleet)

    def set_max_fleet(self, n: int) -> None:
        if not isinstance(n, int) or n <= 0:
            raise ValueError("max fleet must be a positive integer")
        self._default_max_fleet = n

    def set_allowed_subnets(self, subnets: List[str]) -> None:
        if not isinstance(subnets, list):
            raise ValueError("subnets must be a list")
        parsed_networks: List[ipaddress._BaseNetwork] = []
        parsed_prefixes: List[str] = []
        for subnet in subnets:
            if not _is_non_empty_string(subnet):
                raise ValueError("each subnet must be a non-empty string")
            raw = subnet.strip()
            if "/" in raw:
                parsed_networks.append(ipaddress.ip_network(raw, strict=False))
            else:
                parsed_prefixes.append(raw)
        self._allowed_subnets = parsed_networks
        self._allowed_prefixes = parsed_prefixes

    def set_min_classification(self, level: str) -> None:
        self._min_classification = _normalize_classification(level)

    def set_time_window(self, start_hour: int, end_hour: int) -> None:
        if not isinstance(start_hour, int) or not isinstance(end_hour, int):
            raise ValueError("start_hour and end_hour must be integers")
        if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23:
            raise ValueError("start_hour and end_hour must be in [0, 23]")
        if start_hour == end_hour:
            raise ValueError("time window must be non-empty")
        self._time_window = {"start_hour": start_hour, "end_hour": end_hour}

    def evaluate(
        self,
        current_fleet_size: int,
        target_classification: str = "UNCLASSIFIED",
        target_ip: str = "",
        token: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate all policy controls and return violations."""
        if not isinstance(current_fleet_size, int) or current_fleet_size < 0:
            raise ValueError("current_fleet_size must be a non-negative integer")

        violations: List[Dict[str, Any]] = []
        target_level_name = _normalize_classification(target_classification)

        # Rule 1: Classification floor for tactical data handling.
        target_level = CLASSIFICATION_LEVELS[target_level_name]
        min_level = CLASSIFICATION_LEVELS[self._min_classification]
        if target_level < min_level:
            violations.append(
                {
                    "rule": "classification_gate",
                    "detail": (
                        f"target classification {target_level_name} "
                        f"below minimum {self._min_classification}"
                    ),
                }
            )

        # Rule 2: Fleet size cap, optionally constrained by token scope.
        max_fleet = self._default_max_fleet
        if isinstance(token, dict) and isinstance(token.get("max_replicas"), int):
            max_fleet = min(max_fleet, token["max_replicas"])
        if current_fleet_size >= max_fleet:
            violations.append(
                {
                    "rule": "fleet_size_limit",
                    "detail": f"fleet size {current_fleet_size} >= max {max_fleet}",
                }
            )

        # Rule 3: Subnet restriction for secure enclave boundaries.
        if (self._allowed_subnets or self._allowed_prefixes) and target_ip:
            try:
                ip_obj = ipaddress.ip_address(target_ip)
            except ValueError:
                if any(target_ip.startswith(prefix) for prefix in self._allowed_prefixes):
                    ip_allowed = True
                else:
                    ip_allowed = False
            else:
                ip_allowed = any(ip_obj in subnet for subnet in self._allowed_subnets) or any(
                    target_ip.startswith(prefix) for prefix in self._allowed_prefixes
                )
            if not ip_allowed:
                violations.append(
                    {
                        "rule": "subnet_restriction",
                        "detail": f"target IP {target_ip} not in allowed subnets",
                    }
                )

        # Rule 4: UTC time window for operational control windows.
        if self._time_window:
            current_hour = datetime.now(timezone.utc).hour
            start = self._time_window["start_hour"]
            end = self._time_window["end_hour"]
            if start < end:
                in_window = start <= current_hour < end
            else:
                # Supports overnight windows (e.g., 22 -> 04).
                in_window = current_hour >= start or current_hour < end
            if not in_window:
                violations.append(
                    {
                        "rule": "time_window",
                        "detail": f"current UTC hour {current_hour} outside window [{start}, {end})",
                    }
                )

        # Rule 5: Custom callables (fail closed to preserve security posture).
        for rule in self._rules:
            check = rule.get("check")
            if callable(check):
                try:
                    allowed, reason = check(current_fleet_size, target_level_name, target_ip, token)
                except Exception as exc:  # pragma: no cover - defensive fail-closed branch
                    allowed = False
                    reason = f"custom policy rule error: {exc}"
                if not allowed:
                    violations.append(
                        {"rule": rule.get("name", "custom_rule"), "detail": str(reason)}
                    )

        return violations


class GovernedReplicationEngine:
    """
    Security-hardened replication engine with multi-gate enforcement.

    Pipeline:
      1) Token verification
      2) Policy evaluation
      3) Data sovereignty + resource budget gate
      4) Replication execution and immutable audit emission
    """

    def __init__(
        self,
        secret_key: str = "s3m-default-key-CHANGE-IN-PRODUCTION",
        max_fleet: int = 16,
        min_classification: str = "UNCLASSIFIED",
        max_total_memory_mb: int = 65536,
    ) -> None:
        if not _is_non_empty_string(secret_key):
            raise ValueError("secret_key must be a non-empty string")
        if not isinstance(max_total_memory_mb, int) or max_total_memory_mb <= 0:
            raise ValueError("max_total_memory_mb must be a positive integer")

        self.secret_key = secret_key
        self._secret_key = secret_key  # compatibility alias
        self.policy = ReplicationPolicy()
        self.policy.set_max_fleet(max_fleet)
        self.policy.set_min_classification(min_classification)

        self._max_total_memory_mb = max_total_memory_mb
        self._replicas: Dict[str, Dict[str, Any]] = {}
        self._active = self._replicas  # compatibility alias
        self._quarantined: Dict[str, Dict[str, Any]] = {}
        self._killed: List[str] = []
        self._audit_log: List[Dict[str, Any]] = []
        self._audit_callback: Optional[Callable[..., Any]] = None
        self._entity_classification: Dict[str, str] = {}

        logger.info(
            "GovernedReplicationEngine initialized: max_fleet=%d min_classification=%s max_mem=%dMB",
            max_fleet,
            _normalize_classification(min_classification),
            max_total_memory_mb,
        )

    def set_audit_callback(self, callback: Optional[Callable[..., Any]]) -> None:
        """Register SecureAuditLog.log (or equivalent) as audit sink."""
        if callback is not None and not callable(callback):
            raise ValueError("callback must be callable or None")
        self._audit_callback = callback

    def _audit(self, action: str, details: Optional[Dict[str, Any]] = None, severity: str = "INFO", **kwargs: Any) -> None:
        payload: Dict[str, Any] = {}
        if details:
            payload.update(details)
        payload.update(kwargs)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": payload,
            "severity": severity,
        }
        self._audit_log.append(entry)
        if self._audit_callback is not None:
            try:
                self._audit_callback(
                    action=action,
                    details=payload,
                    severity=severity,
                    source="governed_replication",
                )
            except Exception:
                logger.exception("Audit callback failed for action=%s", action)

    def issue_token(
        self,
        issuer: str,
        subject: Optional[str] = None,
        max_replicas: int = 1,
        classification: str = "UNCLASSIFIED",
        ttl_seconds: int = 3600,
        subject_node: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue signed replication authorization token."""
        token = ReplicationToken(
            issuer=issuer,
            subject=subject,
            subject_node=subject_node,
            max_replicas=max_replicas,
            classification=classification,
            ttl_seconds=ttl_seconds,
        )
        token.sign(self.secret_key)
        token_dict = token.to_dict()
        self._audit(
            "token_issued",
            {
                "token_id": token_dict["token_id"],
                "issuer": token_dict["issuer"],
                "subject": token_dict["subject"],
                "max_replicas": token_dict["max_replicas"],
                "classification": token_dict["classification"],
                "expires_at": token_dict["expires_at"],
            },
        )
        return token_dict

    def verify_token(self, token_dict: Dict[str, Any], required_subject: Optional[str] = None) -> bool:
        return ReplicationToken.verify(
            token_dict=token_dict,
            secret_key=self.secret_key,
            required_subject=required_subject,
        )

    def _authorize_admin(self, token: Dict[str, Any]) -> bool:
        if not self.verify_token(token):
            return False
        return str(token.get("issuer", "")).lower() == "admin"

    def replicate(
        self,
        parent_node_id: str,
        parent_params: Dict[str, np.ndarray],
        token: Dict[str, Any],
        target_classification: str = "UNCLASSIFIED",
        target_ip: str = "",
        target_memory_mb: int = 4096,
    ) -> Dict[str, Any]:
        """
        Execute governed replication with Crypto Auth → Policy → Resource Gate.

        Tactical context: this path protects classified model state propagation in
        contested and bandwidth-constrained edge environments.
        """
        if not _is_non_empty_string(parent_node_id):
            raise ValueError("parent_node_id must be a non-empty string")
        if not isinstance(parent_params, dict) or not parent_params:
            raise ValueError("parent_params must be a non-empty dictionary")
        if not all(isinstance(v, np.ndarray) for v in parent_params.values()):
            raise ValueError("all parent_params values must be numpy arrays")
        if not isinstance(target_memory_mb, int) or target_memory_mb <= 0:
            raise ValueError("target_memory_mb must be a positive integer")

        # Gate 1: crypto auth for the exact replicating subject.
        if not self.verify_token(token, required_subject=parent_node_id):
            self._audit(
                "replication_denied",
                {"reason": "invalid_token", "parent": parent_node_id, "gate": "crypto_auth"},
                "WARNING",
            )
            return {"error": "token verification failed", "gate": "crypto_auth"}

        token_class = _normalize_classification(str(token.get("classification", "UNCLASSIFIED")))
        parent_class = self._entity_classification.get(parent_node_id, token_class)
        parent_level = CLASSIFICATION_LEVELS[parent_class]

        # Gate 2: policy-as-code controls.
        try:
            violations = self.policy.evaluate(
                current_fleet_size=len(self._replicas),
                target_classification=target_classification,
                target_ip=target_ip,
                token=token,
            )
        except ValueError as exc:
            self._audit(
                "replication_denied",
                {"reason": "policy_input_invalid", "detail": str(exc), "gate": "policy"},
                "WARNING",
            )
            return {"error": str(exc), "gate": "policy"}

        if violations:
            self._audit(
                "replication_denied",
                {"reason": "policy_violation", "violations": violations, "gate": "policy"},
                "WARNING",
            )
            return {"error": "policy violations", "gate": "policy", "violations": violations}

        # Gate 3: data sovereignty and classification inheritance.
        target_class = _normalize_classification(target_classification)
        if CLASSIFICATION_LEVELS[target_class] < parent_level:
            self._audit(
                "replication_denied",
                {
                    "reason": "data_sovereignty",
                    "parent_classification": parent_class,
                    "target_classification": target_class,
                    "gate": "policy",
                },
                "WARNING",
            )
            return {
                "error": "target classification lower than parent classification",
                "gate": "policy",
            }

        # Gate 4: resource budget control for edge survivability.
        active_memory_mb = sum(int(r.get("target_memory_mb", 0)) for r in self._replicas.values())
        if active_memory_mb + target_memory_mb > self._max_total_memory_mb:
            self._audit(
                "replication_denied",
                {
                    "reason": "resource_budget_exceeded",
                    "active_memory_mb": active_memory_mb,
                    "requested_memory_mb": target_memory_mb,
                    "max_total_memory_mb": self._max_total_memory_mb,
                    "gate": "resource",
                },
                "WARNING",
            )
            return {"error": "resource budget exceeded", "gate": "resource"}

        # Execute replication and record inherited classification.
        model_size_mb = max(
            1e-6,
            float(sum(param.nbytes for param in parent_params.values())) / (1024.0 * 1024.0),
        )
        distillation_ratio = min(1.0, (target_memory_mb * 0.6) / model_size_mb)
        replica_id = str(uuid4())
        replica_info = {
            "replica_id": replica_id,
            "parent_node_id": parent_node_id,
            "target_node": parent_node_id,  # compatibility key for older callers
            "classification": parent_class,
            "distillation_ratio": round(distillation_ratio, 3),
            "target_memory_mb": target_memory_mb,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "token_id": str(token.get("token_id", "")),
            "target_ip": target_ip,
            "param_shapes": {k: list(v.shape) for k, v in parent_params.items()},
        }
        self._replicas[replica_id] = replica_info
        self._entity_classification[parent_node_id] = parent_class
        self._entity_classification[replica_id] = parent_class
        self._audit("replication_executed", dict(replica_info))

        logger.info(
            "Governed replication: parent=%s replica=%s class=%s",
            parent_node_id,
            replica_id[:8],
            parent_class,
        )
        return {"success": True, "replica": replica_info}

    def kill_replica(self, replica_id: str, auth_token: Dict[str, Any]) -> Dict[str, Any]:
        """Remote kill switch command; requires authenticated token."""
        if not _is_non_empty_string(replica_id):
            raise ValueError("replica_id must be a non-empty string")
        if not self.verify_token(auth_token):
            self._audit("kill_denied", {"replica_id": replica_id, "reason": "invalid_token"}, "WARNING")
            return {"error": "invalid authorization token", "gate": "crypto_auth"}

        if replica_id not in self._replicas and replica_id not in self._quarantined:
            return {"error": f"replica {replica_id} not found"}

        self._replicas.pop(replica_id, None)
        self._quarantined.pop(replica_id, None)
        self._killed.append(replica_id)
        self._entity_classification.pop(replica_id, None)
        self._audit("replica_killed", {"replica_id": replica_id}, "CRITICAL")
        return {"success": True, "replica_id": replica_id, "action": "killed"}

    def quarantine_replica(
        self,
        replica_id: str,
        auth_token: Dict[str, Any],
        reason: str = "",
    ) -> Dict[str, Any]:
        """Remote quarantine command; isolates replica without destruction."""
        if not _is_non_empty_string(replica_id):
            raise ValueError("replica_id must be a non-empty string")
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        if not self.verify_token(auth_token):
            self._audit(
                "quarantine_denied",
                {"replica_id": replica_id, "reason": "invalid_token"},
                "WARNING",
            )
            return {"error": "invalid authorization token", "gate": "crypto_auth"}

        if replica_id not in self._replicas:
            return {"error": f"replica {replica_id} not found", "replica_id": replica_id}

        info = self._replicas.pop(replica_id)
        info["status"] = "quarantined"
        info["quarantine_reason"] = reason
        info["quarantined_at"] = datetime.now(timezone.utc).isoformat()
        self._quarantined[replica_id] = info
        self._audit(
            "replica_quarantined",
            {"replica_id": replica_id, "reason": reason},
            "WARNING",
        )
        # Return both new and legacy shapes.
        return {
            "success": True,
            "replica_id": replica_id,
            "action": "quarantined",
            "replica": info,
        }

    def list_active(self) -> List[Dict[str, Any]]:
        return list(self._replicas.values())

    def list_quarantined(self) -> List[Dict[str, Any]]:
        return list(self._quarantined.values())

    def fleet_status(self) -> Dict[str, Any]:
        return {
            "active_replicas": len(self._replicas),
            "quarantined_replicas": len(self._quarantined),
            "killed_total": len(self._killed),
            "audit_entries": len(self._audit_log),
            "active_memory_mb": sum(int(r.get("target_memory_mb", 0)) for r in self._replicas.values()),
        }

    def health_check(self) -> Dict[str, Any]:
        allowed_subnets = [str(subnet) for subnet in self.policy._allowed_subnets]
        allowed_subnets.extend(self.policy._allowed_prefixes)
        return {
            **self.fleet_status(),
            "policy_max_fleet": self.policy._default_max_fleet,
            "policy_min_classification": self.policy._min_classification,
            "policy_allowed_subnets": allowed_subnets,
            "max_total_memory_mb": self._max_total_memory_mb,
        }
