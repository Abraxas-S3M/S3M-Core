"""XiidMCPBroker — policy gate between Cortex planner and XiiD MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from s3m_core.defense.audit.merkle_log import AuditEntry, MerkleAuditLog

from src.cortex.manifest import manifest_digest
from src.cortex.tool_map import XiidToolMap
from src.cortex.transport_mcp import MCPTransport
from src.cortex.xiid_write_envelope import WriteEnvelope


class BrokerError(Exception):
    """Base broker failure."""


class ManifestPinMismatch(BrokerError):
    """Pinned manifest digest no longer matches live MCP manifest."""


class EnvelopeRequired(BrokerError):
    """Mutating action attempted without an approval envelope."""


class EnvelopeRejected(BrokerError):
    """Approval envelope failed validation."""


@dataclass(slots=True)
class BrokerCallResult:
    """Outcome of one broker-mediated MCP action."""

    action: str
    tool: str
    result: Dict[str, Any]
    manifest_digest: str


class XiidMCPBroker:
    """Connects to XiiD MCP, pins tool manifest, and gates writes behind envelopes.

    Tactical context: prevents autonomous agents from mutating the battlespace
    network without an operator-signed approval and an auditable evidence chain.
    """

    def __init__(
        self,
        transport: MCPTransport,
        tool_map: XiidToolMap,
        audit_log: MerkleAuditLog,
        *,
        session_id: str,
        envelope_signing_key: bytes,
    ) -> None:
        self._transport = transport
        self._tool_map = tool_map
        self._audit_log = audit_log
        self._session_id = session_id
        self._envelope_signing_key = envelope_signing_key
        self._pinned_digest: Optional[str] = None
        self._write_dispatched: set[str] = set()

    @property
    def manifest_digest(self) -> Optional[str]:
        return self._pinned_digest

    async def connect_and_pin_manifest(self) -> str:
        tools = await self._transport.list_tools()
        digest = manifest_digest(tools)
        self._pinned_digest = digest
        self._append_audit(
            event_type="mcp_manifest_pinned",
            severity="info",
            details={"manifest_digest": digest, "tool_count": len(tools)},
        )
        return digest

    async def refresh_manifest_guard(self) -> None:
        """Refuse further work when the live manifest no longer matches the pin."""
        if self._pinned_digest is None:
            raise BrokerError("manifest is not pinned")
        tools = await self._transport.list_tools()
        live = manifest_digest(tools)
        if live != self._pinned_digest:
            self._append_audit(
                event_type="mcp_manifest_mismatch",
                severity="critical",
                details={"pinned": self._pinned_digest, "live": live},
            )
            raise ManifestPinMismatch(f"manifest digest mismatch: pinned={self._pinned_digest} live={live}")

    async def invoke(
        self,
        action: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        envelope: Optional[WriteEnvelope] = None,
        idempotency_key: Optional[str] = None,
    ) -> BrokerCallResult:
        await self.refresh_manifest_guard()
        binding = self._tool_map.resolve(action)
        if binding.requires_envelope:
            if envelope is None:
                self._append_audit(
                    event_type="write_denied_missing_envelope",
                    severity="warning",
                    details={"action": action, "tool": binding.tool},
                )
                raise EnvelopeRequired(f"write action {action} requires WriteEnvelope")
            if envelope.action != action or envelope.session_id != self._session_id:
                raise EnvelopeRejected("envelope action/session mismatch")
            if not envelope.verify(self._envelope_signing_key):
                raise EnvelopeRejected("envelope signature invalid")

        if binding.requires_envelope and not idempotency_key:
            dedupe_key = f"{action}:{sorted((arguments or {}).items())!r}"
            if dedupe_key in self._write_dispatched:
                raise BrokerError("duplicate write dispatch blocked at broker gate")

        self._append_audit(
            event_type="mcp_tool_dispatch",
            severity="info",
            details={
                "action": action,
                "tool": binding.tool,
                "idempotency_key": idempotency_key or "",
                "has_envelope": envelope is not None,
            },
        )
        result = await self._transport.call_tool(
            binding.tool,
            arguments,
            idempotency_key=idempotency_key,
        )
        if binding.requires_envelope and not idempotency_key:
            self._write_dispatched.add(f"{action}:{sorted((arguments or {}).items())!r}")
        self._append_audit(
            event_type="mcp_tool_result",
            severity="info",
            details={"action": action, "tool": binding.tool, "result_keys": sorted(result.keys())},
        )
        return BrokerCallResult(
            action=action,
            tool=binding.tool,
            result=result,
            manifest_digest=self._pinned_digest or "",
        )

    def verify_evidence_chain(self) -> bool:
        report = self._audit_log.verify_integrity()
        return report.chain_intact

    def _append_audit(self, *, event_type: str, severity: str, details: Mapping[str, Any]) -> None:
        self._audit_log.append(
            AuditEntry(
                timestamp=datetime.now(timezone.utc),
                session_id=self._session_id,
                event_type=event_type,
                source_layer="cortex.broker",
                severity=severity,
                details=dict(details),
                previous_hash="",
            )
        )
