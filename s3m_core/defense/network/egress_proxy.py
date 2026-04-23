"""Egress proxy for outbound traffic inspection and containment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from multiprocessing import Event, Process
import re
import time
from typing import Dict, List

from .policy_engine import NetworkPolicyEngine, NetworkRequest


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TrafficEntry:
    """Immutable traffic record used for tactical after-action analysis."""

    timestamp: str
    session_id: str
    method: str
    url: str
    request_size: int
    response_code: int
    blocked: bool
    block_reason: str
    content_flags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ExfilAlert:
    """Alert representing likely outbound exfiltration activity."""

    session_id: str
    timestamp: str
    destination: str
    data_type: str
    data_preview: str
    action_taken: str


class EgressProxy:
    """Inspect, decide, and log all outbound traffic from agent containers."""

    _INTERNAL_DATA_PATTERNS = (
        re.compile(r"(?i)\bconfidential\b"),
        re.compile(r"(?i)\binternal[_\s-]?only\b"),
        re.compile(r"(?i)\bmission[_\s-]?plan\b"),
        re.compile(r"(?i)\broe\b|\brules of engagement\b"),
        re.compile(r"(?i)\btarget package\b"),
    )

    def __init__(
        self,
        policy_engine: NetworkPolicyEngine,
        listen_port: int = 8443,
        tls_intercept: bool = True,
    ) -> None:
        if not isinstance(policy_engine, NetworkPolicyEngine):
            raise TypeError("policy_engine must be an instance of NetworkPolicyEngine")
        if not isinstance(listen_port, int) or not 1 <= listen_port <= 65535:
            raise ValueError("listen_port must be an integer in range 1..65535")

        self.policy_engine = policy_engine
        self.listen_port = listen_port
        self.tls_intercept = bool(tls_intercept)
        self._traffic_log: Dict[str, List[TrafficEntry]] = {}
        self._exfil_alerts: List[ExfilAlert] = []
        self._audit_log: List[dict[str, str | int | bool | List[str]]] = []
        self._process: Process | None = None
        self._shutdown_event: Event | None = None

    def start(self) -> None:
        """Start proxy control loop in a separate process."""
        if self._process is not None and self._process.is_alive():
            return

        self._shutdown_event = Event()
        self._process = Process(
            target=self._run_proxy_loop,
            kwargs={"shutdown_event": self._shutdown_event},
            daemon=True,
        )
        self._process.start()

    def handle_request(self, session_id: str, request: NetworkRequest) -> dict:
        """
        Inspect one outbound request and return simulated forwarding response.

        Tactical context:
        This method models a containment chokepoint where all egress is inspected
        before any packet can leave the mission enclave.
        """
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("session_id must be non-empty")
        if not isinstance(request, NetworkRequest):
            raise TypeError("request must be an instance of NetworkRequest")

        normalized_request = NetworkRequest(
            destination_host=request.destination_host,
            destination_port=request.destination_port,
            protocol=request.protocol,
            method=request.method,
            path=request.path,
            body_size=request.body_size,
            content_type=request.content_type,
            body_preview=request.body_preview,
            session_id=normalized_session,
        )

        decision = self.policy_engine.evaluate_request(normalized_request)
        internal_flags = self._scan_internal_data(normalized_request.body_preview)
        content_flags = sorted(set(decision.content_flags + internal_flags))

        blocked = not decision.allowed or bool(internal_flags)
        block_reason = decision.reason
        if decision.allowed and internal_flags:
            block_reason = "Blocked: outbound content appears to contain internal data."

        response_code = 403 if blocked else 200
        response_headers = {
            "x-s3m-egress-proxy": "containment",
            "x-s3m-tls-intercept": "enabled" if self.tls_intercept else "disabled",
        }
        if blocked:
            response_headers["x-s3m-deny-reason"] = block_reason

        url = (
            f"{normalized_request.protocol.lower()}://{normalized_request.destination_host}:"
            f"{normalized_request.destination_port}{normalized_request.path}"
        )
        entry = TrafficEntry(
            timestamp=_utc_now_iso(),
            session_id=normalized_session,
            method=normalized_request.method.upper(),
            url=url,
            request_size=normalized_request.body_size,
            response_code=response_code,
            blocked=blocked,
            block_reason=block_reason if blocked else "",
            content_flags=content_flags,
        )
        self._traffic_log.setdefault(normalized_session, []).append(entry)

        body_hash = hashlib.sha256(normalized_request.body_preview.encode("utf-8")).hexdigest()
        self._audit_log.append(
            {
                "timestamp": entry.timestamp,
                "session_id": normalized_session,
                "url": url,
                "request_method": entry.method,
                "request_size": entry.request_size,
                "response_code": response_code,
                "blocked": blocked,
                "block_reason": block_reason if blocked else "",
                "content_flags": content_flags,
                "body_hash_sha256": body_hash,
            }
        )

        if blocked:
            self._create_exfil_alerts(
                session_id=normalized_session,
                destination=normalized_request.destination_host,
                body_preview=normalized_request.body_preview,
                content_flags=content_flags,
            )

        return {
            "status_code": response_code,
            "headers": response_headers,
            "blocked": blocked,
            "reason": block_reason if blocked else "approved",
        }

    def get_traffic_log(self, session_id: str) -> List[TrafficEntry]:
        """Return traffic entries for one mission session."""
        return list(self._traffic_log.get(session_id, []))

    def get_exfiltration_alerts(self) -> List[ExfilAlert]:
        """Return all exfiltration alerts emitted by the proxy."""
        return list(self._exfil_alerts)

    def _create_exfil_alerts(
        self,
        *,
        session_id: str,
        destination: str,
        body_preview: str,
        content_flags: List[str],
    ) -> None:
        if not content_flags:
            return
        mapping = {
            "credential": "credential",
            "source_code": "source_code",
            "internal_data": "internal_data",
        }
        for flag in content_flags:
            data_type = mapping.get(flag)
            if data_type is None:
                continue
            self._exfil_alerts.append(
                ExfilAlert(
                    session_id=session_id,
                    timestamp=_utc_now_iso(),
                    destination=destination,
                    data_type=data_type,
                    data_preview=body_preview[:128],
                    action_taken="blocked_403",
                )
            )

    def _scan_internal_data(self, body_preview: str) -> List[str]:
        preview = str(body_preview or "")[:1024]
        if any(pattern.search(preview) for pattern in self._INTERNAL_DATA_PATTERNS):
            return ["internal_data"]
        return []

    @staticmethod
    def _run_proxy_loop(*, shutdown_event: Event) -> None:
        # Tactical context: long-lived process placeholder for packet interception
        # integration, kept deterministic for offline edge test environments.
        while not shutdown_event.is_set():
            time.sleep(0.25)
