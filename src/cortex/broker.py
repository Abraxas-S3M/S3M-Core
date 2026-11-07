"""Cortex broker: sole egress for network and system mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from src.cortex.changes import (
    NetworkChange,
    SystemChange,
    apply_network_change,
    apply_system_change,
    broker_authorize,
    broker_reset,
)
from src.cortex.policy_gate import PolicyGate, PolicyGateConfig, PolicyVerdict


class BrokerDenied(RuntimeError):
    """Raised when policy_gate rejects a brokered change."""


class CortexBroker:
    """Routes network/system mutations through policy_gate then low-level applicators."""

    def __init__(
        self,
        *,
        config: PolicyGateConfig,
        evaluator: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self._config = config
        self._evaluator = evaluator

    def execute_network_change(
        self,
        change: NetworkChange,
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        verdict = PolicyGate.evaluate(action, config=self._config, evaluator=self._evaluator)
        if not verdict.allowed:
            raise BrokerDenied(verdict.reason)
        token = broker_authorize()
        try:
            return apply_network_change(change)
        finally:
            broker_reset(token)

    def execute_system_change(
        self,
        change: SystemChange,
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        verdict = PolicyGate.evaluate(action, config=self._config, evaluator=self._evaluator)
        if not verdict.allowed:
            raise BrokerDenied(verdict.reason)
        token = broker_authorize()
        try:
            return apply_system_change(change)
        finally:
            broker_reset(token)
