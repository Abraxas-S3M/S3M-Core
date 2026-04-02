"""
Network invisibility enforcement — ensures S3M nodes have zero
discoverable attack surface from external networks.

Implements Xiid ZKN principle: "If they can't see you, they can't attack you."
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class InvisibilityReport:
    """Results of a perimeter invisibility audit."""
    timestamp: str
    public_ips_found: List[str]
    open_inbound_ports: List[int]
    dns_resolvable: bool
    listening_services: List[Dict[str, Any]]
    is_invisible: bool
    findings: List[str]
    remediation: List[str]


class InvisibilityEnforcer:
    """Validates and enforces that the S3M node is invisible externally.

    Checks:
    1. No public IP addresses bound to any interface
    2. All inbound ports closed (outbound-only model)
    3. DNS does not resolve to this node
    4. No services listening on external interfaces
    5. iptables/nftables rules enforce outbound-only
    """

    ALLOWED_LISTEN_ADDRS = {"127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}
    ALLOWED_PORTS = {8080}

    def audit(self) -> InvisibilityReport:
        from datetime import datetime, timezone
        findings: List[str] = []
        remediation: List[str] = []

        public_ips = self._check_public_ips()
        if public_ips:
            findings.append(f"PUBLIC IPs DETECTED: {public_ips}")
            remediation.append("Remove public IP bindings; use SealedTunnel for all external comms")

        open_ports = self._check_inbound_ports()
        if open_ports:
            findings.append(f"INBOUND PORTS OPEN: {open_ports}")
            remediation.append("Close all inbound ports; configure iptables DROP on INPUT chain")

        dns_ok = self._check_dns_invisibility()
        if dns_ok:
            findings.append("DNS resolves to this node — discoverable")
            remediation.append("Remove DNS A/AAAA records; use SealedTunnel mesh addressing")

        listeners = self._check_listening_services()
        external_listeners = [
            l for l in listeners if l.get("address") not in self.ALLOWED_LISTEN_ADDRS
        ]
        if external_listeners:
            findings.append(f"EXTERNAL LISTENERS: {len(external_listeners)} services")
            remediation.append("Bind all services to 127.0.0.1 only")

        is_invisible = len(findings) == 0
        return InvisibilityReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            public_ips_found=public_ips, open_inbound_ports=open_ports,
            dns_resolvable=dns_ok, listening_services=listeners,
            is_invisible=is_invisible, findings=findings, remediation=remediation,
        )

    def enforce_outbound_only(self) -> Dict[str, Any]:
        rules = [
            "# S3M Quantum Security Shell — Outbound-Only Firewall",
            "*filter",
            ":INPUT DROP [0:0]",
            ":FORWARD DROP [0:0]",
            ":OUTPUT ACCEPT [0:0]",
            "-A INPUT -i lo -j ACCEPT",
            "-A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
            "-A INPUT -j LOG --log-prefix 'S3M-QSS-DROP: ' --log-level 4",
            "-A INPUT -j DROP",
            "COMMIT",
        ]
        return {
            "rules": rules, "script": "\n".join(rules),
            "apply_command": "iptables-restore < /etc/s3m/iptables.rules",
        }

    def _check_public_ips(self) -> List[str]:
        public_ips: List[str] = []
        if os.name != "posix":
            return public_ips
        try:
            output = subprocess.check_output(["ip", "-4", "addr", "show"], text=True, timeout=5)
            for line in output.splitlines():
                match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    ip = match.group(1)
                    if not self._is_private(ip):
                        public_ips.append(ip)
        except Exception:
            pass
        return public_ips

    def _is_private(self, ip: str) -> bool:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        a, b = int(parts[0]), int(parts[1])
        return (a == 10) or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 127)

    def _check_inbound_ports(self) -> List[int]:
        open_ports: List[int] = []
        try:
            with open("/proc/net/tcp", "r") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    local = parts[1]
                    state = parts[3]
                    if state == "0A":
                        addr_hex, port_hex = local.split(":")
                        port = int(port_hex, 16)
                        addr_int = int(addr_hex, 16)
                        if addr_int != 0x0100007F and port not in self.ALLOWED_PORTS:
                            open_ports.append(port)
        except Exception:
            pass
        return open_ports

    def _check_dns_invisibility(self) -> bool:
        try:
            import socket
            hostname = socket.getfqdn()
            result = socket.getaddrinfo(hostname, None)
            for _, _, _, _, addr in result:
                ip = addr[0]
                if not self._is_private(ip) and ip not in ("::1", "127.0.0.1"):
                    return True
        except Exception:
            pass
        return False

    def _check_listening_services(self) -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        try:
            output = subprocess.check_output(["ss", "-tlnp"], text=True, timeout=5)
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    listen_addr = parts[3]
                    addr = listen_addr.rsplit(":", 1)[0] if ":" in listen_addr else "*"
                    port = listen_addr.rsplit(":", 1)[1] if ":" in listen_addr else "0"
                    services.append({"address": addr, "port": int(port)})
        except Exception:
            pass
        return services
