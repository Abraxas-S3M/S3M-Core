"""Network policy engine for tactical outbound containment controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import ipaddress
import re
from typing import Dict, List, Tuple


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class NetworkPolicy:
    """Allowlist-first outbound policy for one mission session envelope."""

    allowed_domains: List[str] = field(default_factory=list)
    allowed_ips: List[str] = field(default_factory=list)
    allowed_ports: List[int] = field(default_factory=list)

    blocked_domains: List[str] = field(default_factory=list)
    blocked_services: List[str] = field(default_factory=list)

    allow_http: bool = True
    allow_https: bool = True
    allow_ssh: bool = False
    allow_dns: bool = True
    allow_raw_sockets: bool = False

    max_upload_bytes_per_request: int = 10_000_000
    max_upload_bytes_per_session: int = 100_000_000
    max_requests_per_minute: int = 60

    block_credential_patterns: bool = True
    block_source_code_upload: bool = True

    def __post_init__(self) -> None:
        self.allowed_domains = [item.strip().lower() for item in self.allowed_domains if item.strip()]
        self.blocked_domains = [item.strip().lower() for item in self.blocked_domains if item.strip()]
        self.blocked_services = [item.strip().lower() for item in self.blocked_services if item.strip()]

        normalized_ports = []
        for port in self.allowed_ports:
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError("allowed_ports must contain integers in range 1..65535")
            normalized_ports.append(port)
        self.allowed_ports = sorted(set(normalized_ports))

        for cidr in self.allowed_ips:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR in allowed_ips: {cidr}") from exc

        if self.max_upload_bytes_per_request < 0:
            raise ValueError("max_upload_bytes_per_request must be >= 0")
        if self.max_upload_bytes_per_session < 0:
            raise ValueError("max_upload_bytes_per_session must be >= 0")
        if self.max_requests_per_minute <= 0:
            raise ValueError("max_requests_per_minute must be > 0")


@dataclass(slots=True)
class NetworkRequest:
    """Normalized request metadata captured before outbound transmission."""

    destination_host: str
    destination_port: int
    protocol: str
    method: str
    path: str
    body_size: int
    content_type: str
    body_preview: str
    session_id: str = "default"

    def __post_init__(self) -> None:
        if not self.destination_host.strip():
            raise ValueError("destination_host must be non-empty")
        if not isinstance(self.destination_port, int) or not 1 <= self.destination_port <= 65535:
            raise ValueError("destination_port must be an integer in range 1..65535")
        if not self.protocol.strip():
            raise ValueError("protocol must be non-empty")
        if not self.method.strip():
            raise ValueError("method must be non-empty")
        if self.body_size < 0:
            raise ValueError("body_size must be >= 0")
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        # Tactical privacy guardrail: only the first 1KB is retained for pattern scans.
        self.body_preview = self.body_preview[:1024]


@dataclass(slots=True)
class PolicyDecision:
    """Final permit/deny decision emitted by policy evaluation."""

    allowed: bool
    reason: str
    content_flags: List[str] = field(default_factory=list)


class NetworkPolicyEngine:
    """Evaluate and enforce outbound containment policy for agent sessions."""

    _CREDENTIAL_PATTERNS: Tuple[re.Pattern[str], ...] = (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}['\"]"),
        re.compile(r"(?i)secret[_-]?key\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
        re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9\-\._~\+/]+=*"),
        re.compile(r"(?i)-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----"),
    )
    _SOURCE_CODE_PATTERNS: Tuple[re.Pattern[str], ...] = (
        re.compile(r"(?m)^\s*def\s+[A-Za-z_][A-Za-z0-9_]*\s*\("),
        re.compile(r"(?m)^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\s*[:\(]"),
        re.compile(r"(?m)^\s*import\s+[A-Za-z0-9_\.]+"),
        re.compile(r"(?m)^\s*from\s+[A-Za-z0-9_\.]+\s+import\s+"),
        re.compile(r"(?m)^\s*#include\s+<[A-Za-z0-9_\/\.]+>"),
    )
    _PROTOCOL_FLAGS = {
        "http": "allow_http",
        "https": "allow_https",
        "ssh": "allow_ssh",
        "dns": "allow_dns",
        "raw_socket": "allow_raw_sockets",
    }

    def __init__(self, default_policy: NetworkPolicy):
        if not isinstance(default_policy, NetworkPolicy):
            raise TypeError("default_policy must be an instance of NetworkPolicy")
        self.default_policy = default_policy
        self._session_upload_totals: Dict[str, int] = {}
        self._session_request_windows: Dict[str, List[datetime]] = {}
        self._container_rule_plans: Dict[str, List[str]] = {}

    def evaluate_request(self, request: NetworkRequest) -> PolicyDecision:
        """Apply protocol, destination, rate, and content gates to one request."""
        if not isinstance(request, NetworkRequest):
            raise TypeError("request must be an instance of NetworkRequest")

        content_flags = self.scan_content(request.body_preview)
        content_block = self._get_content_block_reason(content_flags)
        if content_block is not None:
            self._record_request_attempt(request)
            return PolicyDecision(allowed=False, reason=content_block, content_flags=content_flags)

        protocol = request.protocol.strip().lower()
        protocol_allowed = self._is_protocol_allowed(protocol)
        if not protocol_allowed:
            self._record_request_attempt(request)
            return PolicyDecision(
                allowed=False,
                reason=f"Protocol '{protocol}' is disallowed by policy.",
                content_flags=content_flags,
            )

        if request.destination_port not in self.default_policy.allowed_ports:
            self._record_request_attempt(request)
            return PolicyDecision(
                allowed=False,
                reason=f"Destination port {request.destination_port} is not allowlisted.",
                content_flags=content_flags,
            )

        destination_allowed, destination_reason = self._evaluate_destination(request.destination_host)
        if not destination_allowed:
            self._record_request_attempt(request)
            return PolicyDecision(
                allowed=False,
                reason=destination_reason,
                content_flags=content_flags,
            )

        if request.body_size > self.default_policy.max_upload_bytes_per_request:
            self._record_request_attempt(request)
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Request body exceeds per-request limit: {request.body_size} > "
                    f"{self.default_policy.max_upload_bytes_per_request}."
                ),
                content_flags=content_flags,
            )

        if self._would_exceed_rate_limit(request.session_id):
            self._record_request_attempt(request)
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Session '{request.session_id}' exceeded "
                    f"{self.default_policy.max_requests_per_minute} requests per minute."
                ),
                content_flags=content_flags,
            )

        existing_bytes = self._session_upload_totals.get(request.session_id, 0)
        projected_total = existing_bytes + request.body_size
        if projected_total > self.default_policy.max_upload_bytes_per_session:
            self._record_request_attempt(request)
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Session '{request.session_id}' exceeds upload budget: {projected_total} > "
                    f"{self.default_policy.max_upload_bytes_per_session} bytes."
                ),
                content_flags=content_flags,
            )

        self._record_request_attempt(request)
        self._session_upload_totals[request.session_id] = projected_total
        return PolicyDecision(
            allowed=True,
            reason="Request approved by network containment policy.",
            content_flags=content_flags,
        )

    def apply_to_container(self, container_id: str) -> None:
        """Generate container namespace firewall command plan for orchestration."""
        normalized_id = str(container_id or "").strip()
        if not normalized_id:
            raise ValueError("container_id must be non-empty")

        commands = [
            f"ip netns exec {normalized_id} iptables -P OUTPUT DROP",
            f"ip netns exec {normalized_id} iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            f"ip netns exec {normalized_id} iptables -A OUTPUT -p tcp --dport 53 -j {'ACCEPT' if self.default_policy.allow_dns else 'DROP'}",
        ]
        for port in self.default_policy.allowed_ports:
            commands.append(
                f"ip netns exec {normalized_id} iptables -A OUTPUT -p tcp --dport {port} -j ACCEPT"
            )
        for cidr in self.default_policy.allowed_ips:
            commands.append(
                f"ip netns exec {normalized_id} iptables -A OUTPUT -d {cidr} -j ACCEPT"
            )

        # Tactical context: command plans are staged for a privileged orchestrator
        # so mission runtime can apply containment in the correct namespace safely.
        self._container_rule_plans[normalized_id] = commands

    def get_container_rule_plan(self, container_id: str) -> List[str]:
        """Return generated firewall command plan for one container."""
        return list(self._container_rule_plans.get(container_id, []))

    def scan_content(self, body_preview: str) -> List[str]:
        """Scan outbound content preview for exfiltration markers."""
        preview = str(body_preview or "")[:1024]
        flags: List[str] = []
        if self.default_policy.block_credential_patterns and any(
            pattern.search(preview) for pattern in self._CREDENTIAL_PATTERNS
        ):
            flags.append("credential")
        if self.default_policy.block_source_code_upload and any(
            pattern.search(preview) for pattern in self._SOURCE_CODE_PATTERNS
        ):
            flags.append("source_code")
        return flags

    def _get_content_block_reason(self, content_flags: List[str]) -> str | None:
        if "credential" in content_flags:
            return "Blocked: outbound content appears to contain credentials."
        if "source_code" in content_flags:
            return "Blocked: outbound content appears to contain source code."
        return None

    def _is_protocol_allowed(self, protocol: str) -> bool:
        policy_flag = self._PROTOCOL_FLAGS.get(protocol)
        if policy_flag is None:
            return False
        return bool(getattr(self.default_policy, policy_flag))

    def _evaluate_destination(self, destination_host: str) -> tuple[bool, str]:
        normalized_host = destination_host.strip().lower()
        if not normalized_host:
            return False, "Destination host is empty."

        if self._host_in_list(normalized_host, self.default_policy.blocked_domains):
            return False, f"Destination '{normalized_host}' is explicitly blocked."
        if self._host_in_list(normalized_host, self.default_policy.blocked_services):
            return False, f"Destination service '{normalized_host}' is explicitly blocked."

        host_ip = self._parse_ip(normalized_host)
        if host_ip is not None:
            for cidr in self.default_policy.allowed_ips:
                if host_ip in ipaddress.ip_network(cidr, strict=False):
                    return True, f"IP destination '{normalized_host}' is allowlisted."
            return False, f"IP destination '{normalized_host}' is not in allowlisted CIDRs."

        if self._host_in_list(normalized_host, self.default_policy.allowed_domains):
            return True, f"Domain destination '{normalized_host}' is allowlisted."
        return False, f"Domain destination '{normalized_host}' is not allowlisted."

    @staticmethod
    def _host_in_list(host: str, entries: List[str]) -> bool:
        return any(host == item or host.endswith(f".{item}") for item in entries)

    @staticmethod
    def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        try:
            return ipaddress.ip_address(value)
        except ValueError:
            return None

    def _record_request_attempt(self, request: NetworkRequest) -> None:
        now = _utc_now()
        window = self._session_request_windows.setdefault(request.session_id, [])
        cutoff = now - timedelta(minutes=1)
        window[:] = [timestamp for timestamp in window if timestamp >= cutoff]
        window.append(now)

    def _would_exceed_rate_limit(self, session_id: str) -> bool:
        now = _utc_now()
        window = self._session_request_windows.get(session_id, [])
        cutoff = now - timedelta(minutes=1)
        recent_count = sum(1 for timestamp in window if timestamp >= cutoff)
        return recent_count >= self.default_policy.max_requests_per_minute
