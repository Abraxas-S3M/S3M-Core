"""MCP hardening controls for mission-critical service isolation."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Set


@dataclass(slots=True)
class NetworkPolicy:
    """Network controls for an MCP service container."""

    allowed_egress_cidrs: List[str] = field(default_factory=list)
    allowed_ingress_identities: List[str] = field(default_factory=list)
    blocked_ports: List[int] = field(default_factory=list)

    def fingerprint(self) -> str:
        """Return deterministic fingerprint for tamper detection."""
        material = "|".join(
            [
                ",".join(sorted(self.allowed_egress_cidrs)),
                ",".join(sorted(self.allowed_ingress_identities)),
                ",".join(str(port) for port in sorted(self.blocked_ports)),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class MCPServerConfig:
    """Container isolation and trust controls for a single MCP server."""

    image: str
    allowed_tools: List[str]
    network_policy: NetworkPolicy
    separate_pid_namespace: bool = True
    read_only_rootfs: bool = True
    require_mtls: bool = True
    client_cert_path: Optional[str] = None
    server_cert_path: Optional[str] = None


@dataclass(slots=True, frozen=True)
class MCPDeployment:
    """Immutable deployment handle returned to callers."""

    server_name: str
    container_id: str
    endpoint_url: str
    mtls_enabled: bool


@dataclass(slots=True, frozen=True)
class MCPHealthEvent:
    """One hardening alert emitted by continuous monitoring."""

    timestamp: float
    category: str
    message: str
    critical: bool = True


class MCPHealthStream:
    """Polling stream that surfaces incremental MCP hardening alerts."""

    def __init__(self, poller: Callable[[], List[MCPHealthEvent]]) -> None:
        self._poller = poller
        self._history: List[MCPHealthEvent] = []

    def poll(self) -> List[MCPHealthEvent]:
        """Poll for new health alerts since the previous call."""
        events = self._poller()
        self._history.extend(events)
        return events

    @property
    def history(self) -> List[MCPHealthEvent]:
        """Return all events observed through this stream."""
        return list(self._history)


@dataclass(slots=True)
class _RuntimeState:
    known_good_binary_hash: str
    binary_hash: str
    baseline_command_line: str
    command_line: str
    baseline_network_fingerprint: str
    network_fingerprint: str
    baseline_cert_fingerprint: str
    cert_fingerprint: str
    cert_valid: bool
    baseline_process_identity: str
    process_identity: str
    restart_count: int
    baseline_connections: Set[str]
    active_connections: Set[str]
    baseline_filesystem_digest: str
    filesystem_digest: str
    baseline_registered_tools: Set[str]
    registered_tools: Set[str]
    emitted_alert_keys: Set[str] = field(default_factory=set)


class MCPHardening:
    """
    Enforce tamper-resistant MCP server deployment and verification.

    Tactical context:
    Hardened, isolated containers preserve trust boundaries so an onboard
    agent cannot rewrite mission tooling mid-operation.
    """

    def __init__(self, known_good_hashes: Optional[Dict[str, str]] = None) -> None:
        self._known_good_hashes: Dict[str, str] = dict(known_good_hashes or {})
        self._deployments: Dict[str, MCPDeployment] = {}
        self._runtime_states: Dict[str, _RuntimeState] = {}

    def deploy_mcp_server(self, server_name: str, config: MCPServerConfig) -> MCPDeployment:
        """Deploy an MCP server with mandatory isolation controls."""
        self._validate_server_name(server_name)
        self._validate_config(config)

        container_id = self._make_container_id(server_name=server_name, image=config.image)
        endpoint_url = f"https://{server_name}.mesh.s3m.local:8443"
        command_line = self._build_command_line(server_name=server_name, allowed_tools=config.allowed_tools)
        binary_hash = self._hash_material(f"binary:{config.image}")
        known_good_hash = self._known_good_hashes.get(server_name, binary_hash)
        network_fingerprint = config.network_policy.fingerprint()
        cert_fingerprint = self._build_cert_fingerprint(config=config, server_name=server_name)
        process_identity = self._hash_material(f"{container_id}:{command_line}")[:24]
        filesystem_digest = self._hash_material(f"rootfs:{config.image}:readonly={config.read_only_rootfs}")
        registered_tools = set(config.allowed_tools)

        runtime_state = _RuntimeState(
            known_good_binary_hash=known_good_hash,
            binary_hash=binary_hash,
            baseline_command_line=command_line,
            command_line=command_line,
            baseline_network_fingerprint=network_fingerprint,
            network_fingerprint=network_fingerprint,
            baseline_cert_fingerprint=cert_fingerprint,
            cert_fingerprint=cert_fingerprint,
            cert_valid=(not config.require_mtls) or bool(cert_fingerprint),
            baseline_process_identity=process_identity,
            process_identity=process_identity,
            restart_count=0,
            baseline_connections=set(),
            active_connections=set(),
            baseline_filesystem_digest=filesystem_digest,
            filesystem_digest=filesystem_digest,
            baseline_registered_tools=registered_tools,
            registered_tools=set(registered_tools),
        )

        deployment = MCPDeployment(
            server_name=server_name,
            container_id=container_id,
            endpoint_url=endpoint_url,
            mtls_enabled=config.require_mtls,
        )
        self._deployments[container_id] = deployment
        self._runtime_states[container_id] = runtime_state
        return deployment

    def verify_integrity(self, deployment: MCPDeployment) -> bool:
        """
        Verify binary, process, network, and certificate integrity.

        Checks performed:
        1. Compare current binary hash to known-good value.
        2. Verify process command line has not changed.
        3. Verify network policy fingerprint has not changed.
        4. Verify mTLS certificate fingerprint and validity.
        5. Verify tool registration set is unchanged.
        """
        state = self._get_runtime_state(deployment)
        checks = [
            state.binary_hash == state.known_good_binary_hash,
            state.command_line == state.baseline_command_line,
            state.network_fingerprint == state.baseline_network_fingerprint,
            state.cert_valid and state.cert_fingerprint == state.baseline_cert_fingerprint,
            state.registered_tools == state.baseline_registered_tools,
        ]
        return all(checks)

    def monitor(self, deployment: MCPDeployment) -> MCPHealthStream:
        """Return a continuous monitoring stream for the deployment."""
        self._get_runtime_state(deployment)
        return MCPHealthStream(lambda: self._collect_monitoring_events(deployment.container_id))

    def update_runtime_state(
        self,
        deployment: MCPDeployment,
        *,
        binary_hash: Optional[str] = None,
        command_line: Optional[str] = None,
        network_policy: Optional[NetworkPolicy] = None,
        cert_fingerprint: Optional[str] = None,
        cert_valid: Optional[bool] = None,
        process_identity: Optional[str] = None,
        active_connections: Optional[Set[str]] = None,
        filesystem_digest: Optional[str] = None,
        registered_tools: Optional[Set[str]] = None,
    ) -> None:
        """
        Update observed runtime state from a host monitor pipeline.

        Tactical context:
        Runtime sensor feeds from the platform monitor are folded into this
        state so blue-force defenders can detect control-plane compromise.
        """
        state = self._get_runtime_state(deployment)
        updated = replace(state)

        if binary_hash is not None:
            updated.binary_hash = binary_hash
        if command_line is not None:
            updated.command_line = command_line
        if network_policy is not None:
            updated.network_fingerprint = network_policy.fingerprint()
        if cert_fingerprint is not None:
            updated.cert_fingerprint = cert_fingerprint
        if cert_valid is not None:
            updated.cert_valid = cert_valid
        if process_identity is not None and process_identity != updated.process_identity:
            updated.restart_count += 1
            updated.process_identity = process_identity
        if active_connections is not None:
            updated.active_connections = set(active_connections)
        if filesystem_digest is not None:
            updated.filesystem_digest = filesystem_digest
        if registered_tools is not None:
            updated.registered_tools = set(registered_tools)

        self._runtime_states[deployment.container_id] = updated

    def _collect_monitoring_events(self, container_id: str) -> List[MCPHealthEvent]:
        state = self._runtime_states[container_id]
        events: List[MCPHealthEvent] = []

        if state.process_identity != state.baseline_process_identity and (
            state.command_line != state.baseline_command_line
        ):
            self._append_event_once(
                state,
                events,
                key="process-restart-args",
                category="process_integrity",
                message="Process restart detected with modified command-line arguments",
            )

        new_connections = state.active_connections - state.baseline_connections
        if new_connections:
            self._append_event_once(
                state,
                events,
                key=f"new-connections:{','.join(sorted(new_connections))}",
                category="network_activity",
                message=f"New outbound network connections detected: {sorted(new_connections)}",
            )

        if state.filesystem_digest != state.baseline_filesystem_digest:
            self._append_event_once(
                state,
                events,
                key="filesystem-modified",
                category="filesystem_integrity",
                message="File modifications detected inside MCP server container",
            )

        if not state.cert_valid or state.cert_fingerprint != state.baseline_cert_fingerprint:
            self._append_event_once(
                state,
                events,
                key="certificate-changed",
                category="identity_integrity",
                message="mTLS certificate validity or fingerprint changed unexpectedly",
            )

        if state.network_fingerprint != state.baseline_network_fingerprint:
            self._append_event_once(
                state,
                events,
                key="network-policy-modified",
                category="network_integrity",
                message="MCP network policy fingerprint changed from deployment baseline",
            )

        if state.registered_tools != state.baseline_registered_tools:
            self._append_event_once(
                state,
                events,
                key="tool-registry-drift",
                category="tool_integrity",
                message="Unexpected MCP tool registration or deregistration detected",
            )

        return events

    @staticmethod
    def _append_event_once(
        state: _RuntimeState,
        events: List[MCPHealthEvent],
        *,
        key: str,
        category: str,
        message: str,
    ) -> None:
        if key in state.emitted_alert_keys:
            return
        state.emitted_alert_keys.add(key)
        events.append(
            MCPHealthEvent(
                timestamp=time.time(),
                category=category,
                message=message,
                critical=True,
            )
        )

    def _get_runtime_state(self, deployment: MCPDeployment) -> _RuntimeState:
        state = self._runtime_states.get(deployment.container_id)
        if state is None:
            raise KeyError(f"Unknown deployment container_id '{deployment.container_id}'")
        return state

    @staticmethod
    def _build_command_line(server_name: str, allowed_tools: List[str]) -> str:
        tools = ",".join(sorted(set(allowed_tools)))
        return f"/opt/mcp/bin/{server_name} --tool-allowlist={tools}"

    def _build_cert_fingerprint(self, config: MCPServerConfig, server_name: str) -> str:
        if not config.require_mtls:
            return ""
        cert_material = "|".join(
            [
                server_name,
                config.client_cert_path or f"/etc/mcp/certs/{server_name}-client.crt",
                config.server_cert_path or f"/etc/mcp/certs/{server_name}-server.crt",
            ]
        )
        return self._hash_material(cert_material)

    @staticmethod
    def _make_container_id(server_name: str, image: str) -> str:
        digest = hashlib.sha256(f"{server_name}:{image}".encode("utf-8")).hexdigest()
        return f"mcp-{digest[:12]}"

    @staticmethod
    def _hash_material(material: str) -> str:
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_server_name(server_name: str) -> None:
        if not server_name or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}", server_name):
            raise ValueError("server_name must be 2-64 chars and contain only alnum, '_' or '-'")

    @staticmethod
    def _validate_config(config: MCPServerConfig) -> None:
        if not config.image:
            raise ValueError("image is required")
        if not config.separate_pid_namespace:
            raise ValueError("separate_pid_namespace must remain enabled for tamper resistance")
        if not config.read_only_rootfs:
            raise ValueError("read_only_rootfs must remain enabled for tamper resistance")
        if not config.allowed_tools:
            raise ValueError("allowed_tools must not be empty")
        invalid_tools = [name for name in config.allowed_tools if not re.fullmatch(r"[a-zA-Z0-9_.:-]+", name)]
        if invalid_tools:
            raise ValueError(f"invalid tool name(s): {invalid_tools}")
