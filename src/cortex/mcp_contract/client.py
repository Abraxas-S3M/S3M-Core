"""Cortex client for the control-plane MCP contract v0.1 (implements ``MCPTransport``).

Military/tactical context:
The client is Cortex's side of the trust boundary. It never treats the control plane as
trusted and never lets the AI layer hold write authority:

* identity  - proves possession of its key to the AS (private_key_jwt) and binds every
              request with a fresh DPoP proof; tokens are 5-minute and audience-bound.
* contract  - pins the manifest (contract authority signature + SHA-256) and refuses to
              operate if the server's advertised tools, input or output schemas drift.
* precheck  - runs the same PDP rules locally, so a call outside the sandbox never leaves.
* approvals - attaches approval tokens minted by the independent Approval Authority; the
              client cannot mint them.
* outputs   - validates every result against the contract output schema (unexpected
              fields, oversize text and type confusion are rejected, not passed to the
              planner) and records which fields carry untrusted free text.

It plugs into the existing ``XiidMCPBroker`` unchanged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from src.cortex.mcp_contract.authz import PolicyDecisionPoint, SandboxProfile
from src.cortex.mcp_contract.manifest import ContractManifest, args_sha256, verify_manifest_statement
from src.cortex.mcp_contract.tokens import ClientIdentity, SandboxAuthorizationServer


class ContractError(RuntimeError):
    """Base: carries a contract error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class ContractPinError(ContractError):
    """Manifest signature, digest or advertised schemas do not match the pinned contract."""


class ContractDenied(ContractError):
    """Refused locally (pre-check) or by the control plane."""


class ContractOutputError(ContractError):
    """Control-plane output violated the contract and was discarded."""


def _untrusted_paths(schema_tool: Mapping[str, Any], result: Any, prefix: str = "") -> List[str]:
    """Cheap provenance: field names the contract declares as UntrustedText."""
    out: List[str] = []
    if isinstance(result, dict):
        for k, v in result.items():
            if k in {"summary", "s3m.detail"} and isinstance(v, str):
                out.append(f"{prefix}{k}")
            out.extend(_untrusted_paths(schema_tool, v, f"{prefix}{k}."))
    elif isinstance(result, list):
        for i, v in enumerate(result):
            out.extend(_untrusted_paths(schema_tool, v, f"{prefix}{i}."))
    return out


@dataclass
class CallProvenance:
    tool: str
    sandbox: str
    request_args_sha256: str
    untrusted_fields: List[str] = field(default_factory=list)
    receipt_digest: Optional[str] = None


class ContractMCPTransport:
    def __init__(
        self,
        *,
        url: str,
        resource: str,
        identity: ClientIdentity,
        authorization_server: SandboxAuthorizationServer,
        sandbox: SandboxProfile,
        contract: ContractManifest,
        contract_authority_key: Ed25519PublicKey,
        scopes: Optional[List[str]] = None,
    ) -> None:
        self.url = url
        self.resource = resource
        self.identity = identity
        self.as_server = authorization_server
        self.sandbox = sandbox
        self.contract = contract
        self.authority_key = contract_authority_key
        self.scopes = scopes or sandbox.scopes
        self.precheck = PolicyDecisionPoint({sandbox.sandbox_id: sandbox})
        self.approvals: Dict[Tuple[str, str], str] = {}
        self.provenance: List[CallProvenance] = []
        # Cortex-side write ledger for ProofGuard: exactly what was sent and returned.
        self.write_log: List[Dict[str, Any]] = []
        self._token: Optional[str] = None
        self._claims: Dict[str, Any] = {}
        self._client: Optional[Client] = None
        self._http: Optional[httpx2.AsyncClient] = None
        self.pinned = False

    # ---- identity ----------------------------------------------------------------
    def _ensure_token(self) -> str:
        if self._token and self._claims.get("exp", 0) - 30 > time.time():
            return self._token
        issued = self.as_server.issue_token(
            client_assertion=self.identity.client_assertion(self.as_server.token_endpoint),
            resource=self.resource, sandbox=self.sandbox.sandbox_id, scopes=self.scopes,
            dpop_jkt=self.identity.jkt,
        )
        self._token = issued["access_token"]
        self._claims = jwt.decode(self._token, options={"verify_signature": False})
        return self._token

    async def _sign_request(self, request: httpx2.Request) -> None:
        token = self._ensure_token()
        request.headers["Authorization"] = f"DPoP {token}"
        request.headers["DPoP"] = self.identity.dpop_proof(request.method, self.resource, token)

    async def _open(self) -> Client:
        if self._client is not None:
            return self._client
        self._http = httpx2.AsyncClient(timeout=httpx2.Timeout(30.0), event_hooks={"request": [self._sign_request]})
        self._client = Client(streamable_http_client(self.url, http_client=self._http), mode="legacy")
        await self._client.__aenter__()
        return self._client

    # ---- contract pinning ----------------------------------------------------------
    async def pin_contract(self) -> Dict[str, Any]:
        statement = await self._raw_call("contract.manifest", {})
        if not verify_manifest_statement(statement, self.authority_key):
            raise ContractPinError("CONTRACT_SIGNATURE", "manifest statement not signed by contract authority")
        if statement["manifest_sha256"] != self.contract.sha256:
            raise ContractPinError("CONTRACT_DIGEST", "server manifest differs from the pinned contract")
        drift = self.contract.advertised_matches(await self._advertised())
        if drift:
            raise ContractPinError("CONTRACT_DRIFT", "; ".join(drift[:5]))
        self.pinned = True
        return statement

    async def _advertised(self) -> List[Dict[str, Any]]:
        client = await self._open()
        res = await client.list_tools()
        return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema,
                 "output_schema": t.output_schema} for t in res.tools]

    # ---- MCPTransport protocol ------------------------------------------------------
    async def list_tools(self) -> List[Dict[str, Any]]:
        tools = await self._advertised()
        if self.pinned:
            drift = self.contract.advertised_matches(tools)
            if drift:
                raise ContractPinError("CONTRACT_DRIFT", "; ".join(drift[:5]))
        # inputSchema AND outputSchema feed the broker's manifest digest.
        return [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"],
                 "outputSchema": t["output_schema"]} for t in tools]

    def attach_approval(self, tool: str, arguments: Mapping[str, Any], approval_token: str) -> None:
        self.approvals[(tool, args_sha256(arguments))] = approval_token

    async def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None, *,
                        idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        if not self.pinned:
            await self.pin_contract()
        spec = self.contract.tool(name)
        args = dict(arguments or {})
        self._ensure_token()
        decision = self.precheck.static_check(spec, self._claims, args)
        if not decision.allow:
            raise ContractDenied(decision.code, f"pre-check: {decision.reason}")
        if spec.is_write:
            token = self.approvals.pop((name, args_sha256(args)), None)
            if token is None:
                raise ContractDenied("APPROVAL_REQUIRED", f"no approval token attached for {name}")
            args["approval"] = token
            args["idempotency_key"] = idempotency_key or f"auto-{args_sha256(args)[:24]}"
        errors = self.contract.input_errors(name, args)
        if errors:
            raise ContractDenied("SCHEMA_INVALID", "; ".join(errors))
        result = await self._raw_call(name, args)
        out_errors = self.contract.output_errors(name, result)
        if out_errors:
            raise ContractOutputError("OUTPUT_REJECTED", "; ".join(out_errors))
        if spec.is_write and isinstance(result, dict) and "receipt" in result:
            self.write_log.append({
                "tool": name,
                "client_id": self.identity.client_id,
                "arguments": {k: v for k, v in args.items() if k != "approval"},
                "approval": args.get("approval"),
                "response": result,
                "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        self.provenance.append(CallProvenance(
            tool=name, sandbox=self.sandbox.sandbox_id, request_args_sha256=args_sha256(args),
            untrusted_fields=_untrusted_paths({}, result)[:50],
            receipt_digest=(result.get("receipt") or {}).get("record_digest") if isinstance(result, dict) else None,
        ))
        return result

    async def _raw_call(self, name: str, args: Mapping[str, Any]) -> Dict[str, Any]:
        client = await self._open()
        res = await client.call_tool(name, dict(args))
        if res.is_error:
            text = " ".join(getattr(c, "text", "") for c in res.content)
            code, message = "INTERNAL", text[:300]
            if "{" in text:
                try:
                    err = json.loads(text[text.index("{"):])["error"]
                    code, message = err["code"], err["message"]
                except (ValueError, KeyError):
                    pass
            raise ContractDenied(code, message)
        data = res.structured_content
        if not isinstance(data, dict):
            raise ContractOutputError("OUTPUT_REJECTED", "non-object structured content")
        return data

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None
