"""Unit tests for dual-engine Cortex policy gate."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.cyber.policy_gate import AuthorityWriteRequest, PolicyGate

REPO_ROOT = Path(__file__).resolve().parents[1]
OPA_POLICY_ROOT = REPO_ROOT / "configs" / "opa_policies"


def _happy_request(**overrides) -> AuthorityWriteRequest:
    payload = {
        "change_id": "CHG-1",
        "requested_action": "isolate_host",
        "actor_id": "op-7",
        "actor_grants": ("isolate_host", "rotate_cred"),
        "parent_grants": ("isolate_host", "rotate_cred", "quarantine_net"),
        "approval_operator_id": "op-7",
        "approval_duress": False,
        "approvals_for_change": 2,
        "required_approvals": 2,
    }
    payload.update(overrides)
    return AuthorityWriteRequest(**payload)


def test_evaluate_denies_when_python_checks_fail() -> None:
    gate = PolicyGate()
    result = gate.evaluate(_happy_request(approval_duress=True))
    assert result.allow is False
    assert result.python_allow is False
    assert result.opa_allow is None


def test_evaluate_denies_on_opa_disagreement() -> None:
    def _command_runner(command, **kwargs):
        payload = {"result": [{"expressions": [{"value": False}]}]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    gate = PolicyGate(
        opa_binary="opa",
        opa_policy_dir=OPA_POLICY_ROOT,
        command_runner=_command_runner,
    )
    result = gate.evaluate(_happy_request())
    assert result.allow is False
    assert result.python_allow is True
    assert result.opa_allow is False
    assert result.disagreement is True


def test_evaluate_denies_when_opa_unavailable() -> None:
    def _command_runner(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="missing")

    gate = PolicyGate(
        opa_binary="/nonexistent/opa",
        opa_policy_dir=OPA_POLICY_ROOT,
        command_runner=_command_runner,
        opa_unix_socket="/nonexistent/cortex.sock",
    )
    result = gate.evaluate(_happy_request())
    assert result.allow is False
    assert result.python_allow is True
    assert result.opa_allow is None
    assert "OPA unavailable" in result.deny_reason


def test_evaluate_allows_when_both_engines_agree() -> None:
    opa_binary = REPO_ROOT / "tools" / "bin" / "opa"
    if not opa_binary.exists():
        pytest.skip("pinned OPA binary not installed")
    gate = PolicyGate(opa_binary=str(opa_binary), opa_policy_dir=OPA_POLICY_ROOT)
    result = gate.evaluate(_happy_request())
    assert result.allow is True
    assert result.python_allow is True
    assert result.opa_allow is True
