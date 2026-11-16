"""Policy decision point (PDP) for the Cortex control-plane MCP contract.

Military/tactical context:
Authorisation lives outside any language model. Every call is decided in a fixed order,
and the first failing rule names the refusal code, so an operator can see exactly which
boundary held. The same PDP runs inside the control plane (authoritative) and inside the
Cortex client (pre-check, so a denied call never leaves the enclave).

Decision order:
 1. sandbox known and token bound to it
 2. scope covers the tool's class                      -> FORBIDDEN_SCOPE
 3. sandbox allows the class and the tool name         -> SANDBOX_DENIED
 4. resource arguments match the sandbox selectors     -> RESOURCE_DENIED
 5. writes: sandbox inverse requirement                -> SANDBOX_DENIED
 6. writes: approval present / valid / sufficient      -> APPROVAL_*
 7. writes: approval single use                        -> APPROVAL_REPLAYED
 8. writes: budget within window                       -> WRITE_BUDGET_EXHAUSTED
 9. per-client rate limit                              -> RATE_LIMITED
"""

from __future__ import annotations

import fnmatch
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, Optional

import yaml

from src.cortex.mcp_contract.manifest import CLASS_SCOPE, ToolSpec

SANDBOX_FILE = Path(__file__).resolve().parents[3] / "configs" / "cortex" / "mcp_sandboxes.yaml"


@dataclass(frozen=True)
class SandboxProfile:
    sandbox_id: str
    raw: Mapping[str, Any]

    @property
    def environment(self) -> str:
        return str(self.raw.get("environment", "sandbox"))

    @property
    def scopes(self) -> List[str]:
        return list(self.raw.get("scopes", []))

    @property
    def classes(self) -> List[str]:
        return list(self.raw.get("classes", []))

    @property
    def write_budget(self) -> Mapping[str, int]:
        return self.raw.get("write_budget", {"max_writes": 0, "window_seconds": 3600})

    @property
    def rate_limit(self) -> int:
        return int(self.raw.get("rate_limit_per_minute", 60))

    @property
    def obligations(self) -> Mapping[str, Any]:
        return self.raw.get("obligations", {})

    def tool_allowed(self, name: str) -> bool:
        tools = self.raw.get("tools", {})
        if any(fnmatch.fnmatchcase(name, p) for p in tools.get("allow", [])):
            # explicit allow beats a catch-all deny ("*"), specific deny beats allow
            deny = [p for p in tools.get("deny", []) if p != "*"]
            return not any(fnmatch.fnmatchcase(name, p) for p in deny)
        return False

    def resource_allowed(self, kind: str, resource_id: str) -> bool:
        sel = self.raw.get("resources", {}).get(kind)
        if sel is None:
            return False
        if any(fnmatch.fnmatchcase(resource_id, p) for p in sel.get("deny", [])):
            return False
        return any(fnmatch.fnmatchcase(resource_id, p) for p in sel.get("allow", []))


def load_sandboxes(path: Path = SANDBOX_FILE) -> Dict[str, SandboxProfile]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {sid: SandboxProfile(sid, spec) for sid, spec in raw["profiles"].items()}


@dataclass
class Decision:
    allow: bool
    code: str = "OK"
    reason: str = ""
    obligations: Mapping[str, Any] = field(default_factory=dict)
    approval: Optional[Mapping[str, Any]] = None


def _deny(code: str, reason: str) -> Decision:
    return Decision(False, code, reason)


class PolicyDecisionPoint:
    """Stateful PDP: holds replay, budget and rate windows per client."""

    def __init__(self, sandboxes: Mapping[str, SandboxProfile], *, approval_verifier=None) -> None:
        self.sandboxes = dict(sandboxes)
        self._approval_verifier = approval_verifier  # callable(token, tool, arguments, client_id) -> claims
        self._used_approvals: Dict[str, float] = {}
        self._writes: Dict[str, Deque[float]] = {}
        self._calls: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self.kill_switch = False

    def static_check(self, spec: ToolSpec, claims: Mapping[str, Any], arguments: Mapping[str, Any]) -> Decision:
        """Rules 1-5: no state, no signatures. Safe for client-side pre-checks."""
        sandbox = self.sandboxes.get(str(claims.get("sandbox", "")))
        if sandbox is None:
            return _deny("SANDBOX_DENIED", "token is not bound to a known sandbox")
        scopes = set(str(claims.get("scope", "")).split())
        if CLASS_SCOPE[spec.tool_class] not in scopes or spec.scope not in sandbox.scopes:
            return _deny("FORBIDDEN_SCOPE", f"{spec.name} needs scope {spec.scope}")
        if spec.tool_class not in sandbox.classes or not sandbox.tool_allowed(spec.name):
            return _deny("SANDBOX_DENIED", f"{sandbox.sandbox_id} does not permit {spec.name}")
        if spec.is_write:
            for arg, kind in spec.resource_args.items():
                rid = arguments.get(arg)
                if rid is None or not sandbox.resource_allowed(kind, str(rid)):
                    return _deny("RESOURCE_DENIED", f"{sandbox.sandbox_id} does not permit writes to {kind} {rid}")
            if sandbox.raw.get("require_inverse") and not (spec.inverse or spec.raw.get("write", {}).get("reversible")):
                return _deny("SANDBOX_DENIED", f"{sandbox.sandbox_id} only permits changes with an inverse tool")
        return Decision(True, obligations=dict(sandbox.obligations))

    def decide(self, spec: ToolSpec, claims: Mapping[str, Any], arguments: Mapping[str, Any]) -> Decision:
        """Full decision (control-plane side)."""
        client_id = str(claims.get("client_id") or claims.get("sub"))
        if spec.is_write and self.kill_switch:
            return _deny("KILL_SWITCH_ENGAGED", "writes halted by kill switch")
        d = self.static_check(spec, claims, arguments)
        if not d.allow:
            return d
        sandbox = self.sandboxes[str(claims["sandbox"])]
        approval_claims = None
        if spec.is_write:
            token = arguments.get("approval")
            if not token:
                return _deny("APPROVAL_REQUIRED", f"{spec.name} requires an approval token")
            if self._approval_verifier is None:
                return _deny("APPROVAL_INVALID", "no approval authority configured")
            try:
                approval_claims = self._approval_verifier(str(token), spec.name, arguments, client_id)
            except Exception as exc:  # AuthError carries its own code
                return _deny(getattr(exc, "code", "APPROVAL_INVALID"), str(exc)[:200])
            needed = max(spec.min_approvals, int(sandbox.raw.get("min_approvals", 1)))
            if int(approval_claims.get("approvals", 0)) < needed:
                return _deny("APPROVAL_INSUFFICIENT", f"{spec.name} needs {needed} distinct approvals")
        now = time.time()
        with self._lock:
            calls = self._calls.setdefault(client_id, deque())
            tool_calls = self._calls.setdefault(f"{client_id}|{spec.name}", deque())
            for q in (calls, tool_calls):
                while q and q[0] < now - 60:
                    q.popleft()
            if len(calls) >= sandbox.rate_limit:
                return _deny("RATE_LIMITED", f"{sandbox.sandbox_id} per-minute call limit reached")
            if len(tool_calls) >= int(spec.raw.get("rate_limit_per_minute", 10_000)):
                return _deny("RATE_LIMITED", f"{spec.name} per-minute limit reached")
            if spec.is_write:
                assert approval_claims is not None
                jti = str(approval_claims["jti"])
                for k in [k for k, exp in self._used_approvals.items() if exp < now]:
                    del self._used_approvals[k]
                if jti in self._used_approvals:
                    return _deny("APPROVAL_REPLAYED", "approval token already used")
                window = int(sandbox.write_budget.get("window_seconds", 3600))
                writes = self._writes.setdefault(client_id, deque())
                while writes and writes[0] < now - window:
                    writes.popleft()
                if len(writes) >= int(sandbox.write_budget.get("max_writes", 0)):
                    return _deny("WRITE_BUDGET_EXHAUSTED", f"{sandbox.sandbox_id} write budget exhausted")
                self._used_approvals[jti] = float(approval_claims["exp"]) + 60
                writes.append(now)
            calls.append(now)
            tool_calls.append(now)
        return Decision(True, obligations=d.obligations, approval=approval_claims)
