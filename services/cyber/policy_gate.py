"""Dual-engine policy gate for Cortex defensive write operations.

Military/tactical context: mission cyber teams require independent Python and
OPA authority checks so a compromised control path cannot authorize live changes
without consensus across policy engines.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("s3m.cyber.policy_gate")

# Pinned edge path for offline Jetson deployments; override only in test harnesses.
DEFAULT_OPA_BINARY = os.environ.get(
    "S3M_OPA_BINARY",
    str(Path(__file__).resolve().parents[2] / "tools" / "bin" / "opa"),
)
DEFAULT_OPA_POLICY_DIR = Path(__file__).resolve().parents[2] / "configs" / "opa_policies"
DEFAULT_OPA_DATA_REF = "data.s3m.cortex.authority.final_allow"
DEFAULT_OPA_SOCKET = os.environ.get("S3M_OPA_UNIX_SOCKET", "/var/run/opa/cortex.sock")
OPA_EVAL_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class AuthorityWriteRequest:
    """Validated write intent issued by a tactical cyber operator."""

    change_id: str
    requested_action: str
    actor_id: str
    actor_grants: tuple[str, ...]
    parent_grants: tuple[str, ...]
    approval_operator_id: str
    approval_duress: bool
    approvals_for_change: int
    required_approvals: int

    def validate(self) -> None:
        if not self.change_id.strip():
            raise ValueError("change_id is required")
        if not self.requested_action.strip():
            raise ValueError("requested_action is required")
        if not self.actor_id.strip():
            raise ValueError("actor_id is required")
        if self.required_approvals < 1:
            raise ValueError("required_approvals must be >= 1")
        if self.approvals_for_change < 0:
            raise ValueError("approvals_for_change must be >= 0")


@dataclass
class PolicyEvaluation:
    """Normalized gate decision returned to mission orchestration layers."""

    allow: bool
    python_allow: bool
    opa_allow: bool | None
    deny_reason: str = ""
    disagreement: bool = False


@dataclass
class PolicyGate:
    """Enforces independent Python and OPA allow decisions before writes."""

    opa_binary: str = DEFAULT_OPA_BINARY
    opa_policy_dir: Path = field(default_factory=lambda: DEFAULT_OPA_POLICY_DIR)
    opa_data_ref: str = DEFAULT_OPA_DATA_REF
    opa_unix_socket: str = DEFAULT_OPA_SOCKET
    command_runner: Callable[..., Any] = subprocess.run
    opa_timeout_seconds: float = OPA_EVAL_TIMEOUT_SECONDS

    def _python_allow(self, request: AuthorityWriteRequest) -> tuple[bool, str]:
        if request.approval_duress:
            return False, "duress approval cannot authorize writes"
        if request.actor_id != request.approval_operator_id:
            return False, "approving operator must match acting operator"
        if request.requested_action not in set(request.actor_grants):
            return False, "requested action outside actor grants"
        child = set(request.actor_grants)
        parent = set(request.parent_grants)
        if child - parent:
            return False, "envelope attenuation violation"
        if request.approvals_for_change < request.required_approvals:
            return False, "insufficient non-duress approvals"
        return True, ""

    def _build_opa_input(self, request: AuthorityWriteRequest, python_allow: bool) -> dict[str, Any]:
        return {
            "python": {"allow": python_allow},
            "actor": {"id": request.actor_id, "grants": list(request.actor_grants)},
            "parent": {"grants": list(request.parent_grants)},
            "approval": {
                "operator_id": request.approval_operator_id,
                "duress": request.approval_duress,
            },
            "requested_action": request.requested_action,
            "change_id": request.change_id,
            "required_approvals": request.required_approvals,
            "approvals_for_change": request.approvals_for_change,
        }

    def _extract_opa_bool(self, payload: dict[str, Any]) -> bool | None:
        if "result" not in payload:
            return None
        result_value = payload.get("result")
        if isinstance(result_value, list):
            if not result_value:
                return None
            first = result_value[0] if isinstance(result_value[0], dict) else {}
            expressions = first.get("expressions", []) if isinstance(first, dict) else []
            if not expressions:
                return None
            expression = expressions[0] if isinstance(expressions[0], dict) else {}
            value = expression.get("value")
            return value if isinstance(value, bool) else None
        if isinstance(result_value, bool):
            return result_value
        return None

    def _evaluate_with_opa_binary(self, opa_input: dict[str, Any]) -> bool | None:
        if not Path(self.opa_binary).exists() and self.opa_binary == DEFAULT_OPA_BINARY:
            # Fall back to PATH only when operators intentionally did not vendor the binary.
            if not Path(self.opa_binary).exists():
                self.opa_binary = "opa"
        policy_dir = self.opa_policy_dir
        if not policy_dir.exists():
            return None
        input_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
                input_path = handle.name
                json.dump(opa_input, handle, ensure_ascii=True)
            command = [
                self.opa_binary,
                "eval",
                "--format=json",
                "--data",
                str(policy_dir),
                "--input",
                input_path,
                self.opa_data_ref,
            ]
            completed = self.command_runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.opa_timeout_seconds,
            )
            if getattr(completed, "returncode", 1) != 0:
                return None
            payload = json.loads(getattr(completed, "stdout", "{}") or "{}")
            return self._extract_opa_bool(payload)
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError, json.JSONDecodeError):
            return None
        finally:
            if input_path:
                try:
                    Path(input_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def _evaluate_with_opa_unix_socket(self, opa_input: dict[str, Any]) -> bool | None:
        socket_path = self.opa_unix_socket
        if not socket_path or not Path(socket_path).exists():
            return None
        request_body = json.dumps({"input": opa_input}, ensure_ascii=True).encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.opa_timeout_seconds)
                client.connect(socket_path)
                path = "/v1/data/s3m/cortex/authority/final_allow"
                http_request = (
                    f"POST {path} HTTP/1.0\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(request_body)}\r\n\r\n"
                ).encode("utf-8") + request_body
                client.sendall(http_request)
                response = client.recv(65536)
            body = response.split(b"\r\n\r\n", 1)
            if len(body) != 2:
                return None
            payload = json.loads(body[1].decode("utf-8"))
            result = payload.get("result")
            if isinstance(result, bool):
                return result
            return None
        except (OSError, ValueError, json.JSONDecodeError, TimeoutError):
            return None

    def _evaluate_with_opa(self, opa_input: dict[str, Any]) -> bool | None:
        binary_result = self._evaluate_with_opa_binary(opa_input)
        if binary_result is not None:
            return binary_result
        return self._evaluate_with_opa_unix_socket(opa_input)

    def evaluate(self, request: AuthorityWriteRequest) -> PolicyEvaluation:
        request.validate()
        python_allow, deny_reason = self._python_allow(request)
        if not python_allow:
            return PolicyEvaluation(
                allow=False,
                python_allow=False,
                opa_allow=None,
                deny_reason=deny_reason,
            )

        opa_input = self._build_opa_input(request, python_allow=True)
        opa_allow = self._evaluate_with_opa(opa_input)
        if opa_allow is None:
            logger.error(
                "HIGH_SEVERITY policy_gate_opa_unavailable change_id=%s actor_id=%s",
                request.change_id,
                request.actor_id,
            )
            return PolicyEvaluation(
                allow=False,
                python_allow=True,
                opa_allow=None,
                deny_reason="OPA unavailable or timed out",
            )

        if opa_allow != python_allow:
            logger.error(
                "HIGH_SEVERITY policy_gate_engine_disagreement change_id=%s actor_id=%s python=%s opa=%s",
                request.change_id,
                request.actor_id,
                python_allow,
                opa_allow,
            )
            return PolicyEvaluation(
                allow=False,
                python_allow=python_allow,
                opa_allow=opa_allow,
                deny_reason="policy engine disagreement",
                disagreement=True,
            )

        if not opa_allow:
            return PolicyEvaluation(
                allow=False,
                python_allow=True,
                opa_allow=False,
                deny_reason="OPA denied write",
            )

        return PolicyEvaluation(allow=True, python_allow=True, opa_allow=True)
