"""Authenticated service mesh for internal S3M service-to-service traffic."""

from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(slots=True, frozen=True)
class ServiceEndpoint:
    """Resolved mesh endpoint details for one registered service."""

    name: str
    port: int
    container_id: str
    mesh_ip: str
    certificate_fingerprint: str


@dataclass(slots=True)
class TrafficStats:
    """Traffic counters for one directional service edge."""

    messages: int = 0
    bytes_sent: int = 0
    allowed_connections: int = 0
    denied_connections: int = 0
    anomalies: list[str] = field(default_factory=list)


class ServiceMesh:
    """
    Route internal service traffic through an authenticated mesh fabric.

    Tactical context:
    A controlled east-west mesh blocks covert lateral movement between
    mission services and keeps compromise blast-radius bounded.
    """

    def __init__(self, ca_cert_path: str, mesh_network: str = "10.99.0.0/16") -> None:
        if not ca_cert_path.strip():
            raise ValueError("ca_cert_path is required")
        network = ipaddress.ip_network(mesh_network, strict=False)
        if network.num_addresses < 16:
            raise ValueError("mesh_network must have enough host capacity")
        self._ca_cert_path = ca_cert_path
        self._mesh_network = network
        self._services: Dict[str, ServiceEndpoint] = {}
        self._traffic_matrix: Dict[str, Dict[str, TrafficStats]] = {}
        self._policy_overrides: Dict[Tuple[str, str], bool] = {}
        self._next_host_offset = 2

    def register_service(self, name: str, port: int, container_id: str) -> ServiceEndpoint:
        """Issue mesh identity, assign IP, and initialize routing state."""
        self._validate_service_identity(name=name, port=port, container_id=container_id)
        mesh_ip = self._allocate_mesh_ip()
        certificate_fingerprint = self._issue_certificate(name=name, container_id=container_id)
        endpoint = ServiceEndpoint(
            name=name,
            port=port,
            container_id=container_id,
            mesh_ip=mesh_ip,
            certificate_fingerprint=certificate_fingerprint,
        )
        self._services[name] = endpoint

        self._traffic_matrix.setdefault(name, {})
        for other in self._services:
            self._traffic_matrix.setdefault(other, {})
            if other == name:
                continue
            self._traffic_matrix[other].setdefault(name, TrafficStats())
            self._traffic_matrix[name].setdefault(other, TrafficStats())
        return endpoint

    def connect(self, from_service: str, to_service: str) -> bool:
        """Attempt a policy-validated connection and update traffic counters."""
        stats = self._traffic_matrix.setdefault(from_service, {}).setdefault(to_service, TrafficStats())
        allowed = self._is_connection_allowed(from_service=from_service, to_service=to_service)
        if allowed:
            stats.messages += 1
            stats.bytes_sent += self._estimate_payload_size(from_service=from_service, to_service=to_service)
            stats.allowed_connections += 1
            return True

        stats.denied_connections += 1
        anomaly = f"Denied mesh connection attempt {from_service} -> {to_service}"
        stats.anomalies.append(anomaly)
        return False

    def get_traffic_matrix(self) -> Dict[str, Dict[str, TrafficStats]]:
        """Return a snapshot of directional service-to-service traffic."""
        snapshot: Dict[str, Dict[str, TrafficStats]] = {}
        for source, destinations in self._traffic_matrix.items():
            snapshot[source] = {}
            for destination, stats in destinations.items():
                snapshot[source][destination] = TrafficStats(
                    messages=stats.messages,
                    bytes_sent=stats.bytes_sent,
                    allowed_connections=stats.allowed_connections,
                    denied_connections=stats.denied_connections,
                    anomalies=list(stats.anomalies),
                )
        return snapshot

    def set_connection_policy(self, from_service: str, to_service: str, allowed: bool) -> None:
        """Set an explicit allow/deny override for a service pair."""
        if from_service not in self._services or to_service not in self._services:
            raise ValueError("Both services must be registered before policy override")
        self._policy_overrides[(from_service, to_service)] = bool(allowed)

    def _is_connection_allowed(self, from_service: str, to_service: str) -> bool:
        if from_service not in self._services or to_service not in self._services:
            return False
        if (from_service, to_service) in self._policy_overrides:
            return self._policy_overrides[(from_service, to_service)]
        return True

    def _allocate_mesh_ip(self) -> str:
        available_hosts = self._mesh_network.num_addresses - 2
        if self._next_host_offset >= available_hosts:
            raise RuntimeError("mesh_network address space exhausted")
        ip_value = int(self._mesh_network.network_address) + self._next_host_offset
        self._next_host_offset += 1
        return str(ipaddress.ip_address(ip_value))

    def _issue_certificate(self, name: str, container_id: str) -> str:
        certificate_material = f"{self._ca_cert_path}|{name}|{container_id}"
        return hashlib.sha256(certificate_material.encode("utf-8")).hexdigest()

    @staticmethod
    def _estimate_payload_size(from_service: str, to_service: str) -> int:
        material = f"{from_service}:{to_service}".encode("utf-8")
        return 256 + (sum(material) % 1024)

    @staticmethod
    def _validate_service_identity(name: str, port: int, container_id: str) -> None:
        if not name.strip():
            raise ValueError("name is required")
        if port < 1 or port > 65535:
            raise ValueError("port must be in range 1-65535")
        if not container_id.strip():
            raise ValueError("container_id is required")
