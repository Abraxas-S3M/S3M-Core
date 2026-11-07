"""Cortex reasoning brain for the XiiD MCP cybersecurity agent."""

from src.cortex.broker import BrokerDenied, CortexBroker
from src.cortex.changes import BrokerBypassError
from src.cortex.config import CortexConfig, load_cortex_config
from src.cortex.policy_gate import Approval, MissionEnvelope, PolicyGate, PolicyVerdict
from src.cortex.runtime import ProductionDependencyError, assert_production_dependencies
from src.cortex.taint import TaintSource, TaintedPayload, wrap_untrusted
from src.cortex.tools import assert_tool_permitted, forbidden_tool_reason
from src.cortex.case_report import CaseEvidencePack, generate_case_report
from src.cortex.scenario_b import run_scenario_b

__all__ = [
    "CaseEvidencePack",
    "generate_case_report",
    "run_scenario_b",
    "Approval",
    "BrokerBypassError",
    "BrokerDenied",
    "CortexBroker",
    "CortexConfig",
    "MissionEnvelope",
    "PolicyGate",
    "PolicyVerdict",
    "ProductionDependencyError",
    "TaintSource",
    "TaintedPayload",
    "assert_production_dependencies",
    "assert_tool_permitted",
    "forbidden_tool_reason",
    "load_cortex_config",
    "wrap_untrusted",
]
