"""CoT network transport for multicast and TAK-server tactical links."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

import yaml


class CotTransport:
    """Manage CoT sockets and offline outbox fallback for austere operations."""

    _TAK_V0_HEADER = bytes([0xBF, 0x00, 0xBF])

    def __init__(self, config: dict):
        merged = self._load_config(config)
        self.multicast_address = str(merged.get("multicast_address", "239.2.3.1"))
        self.multicast_port = int(merged.get("multicast_port", 6969))
        self.tak_server_url = merged.get("tak_server_url")
        self.tak_protocol_version = int(merged.get("tak_protocol_version", 0))
        self.outbox_dir = Path(str(merged.get("outbox_dir", "data/interop/cot_outbox/")))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        self.transport_type: Optional[str] = None
        self.multicast_socket: Optional[socket.socket] = None
        self.tak_socket: Optional[socket.socket] = None
        self.connected = False
        self.messages_sent = 0
        self.messages_received = 0
        self._tcp_buffer = b""

    def connect_multicast(self) -> bool:
        """Join CoT multicast group over UDP."""
        self.disconnect()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.multicast_port))
            membership = socket.inet_aton(self.multicast_address) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            sock.setblocking(False)
            self.multicast_socket = sock
            self.transport_type = "multicast"
            self.connected = True
            return True
        except OSError:
            self.disconnect()
            return False

    def connect_tak_server(self, url: str) -> bool:
        """Connect to TAK Server over persistent TCP."""
        if url:
            self.tak_server_url = str(url).strip()
        if not self.tak_server_url:
            self.disconnect()
            return False

        host, port = self._parse_tak_url(self.tak_server_url)
        self.disconnect()
        try:
            sock = socket.create_connection((host, port), timeout=2.5)
            sock.setblocking(False)
            self.tak_socket = sock
            self.transport_type = "tak_server"
            self.connected = True
            return True
        except OSError:
            self.disconnect()
            return False

    def send(self, xml: str) -> bool:
        """Send CoT XML over active transport or queue offline when unavailable."""
        payload = str(xml or "").strip()
        if not payload:
            return False
        data = payload.encode("utf-8")

        try:
            if self.transport_type == "multicast" and self.multicast_socket is not None:
                self.multicast_socket.sendto(data, (self.multicast_address, self.multicast_port))
                self.messages_sent += 1
                return True

            if self.transport_type == "tak_server":
                if self.tak_socket is None and not self._reconnect_tak():
                    self._write_outbox(payload)
                    return False
                frame = self._TAK_V0_HEADER + data if self.tak_protocol_version == 0 else data
                try:
                    assert self.tak_socket is not None
                    self.tak_socket.sendall(frame)
                    self.messages_sent += 1
                    return True
                except OSError:
                    if self._reconnect_tak():
                        assert self.tak_socket is not None
                        self.tak_socket.sendall(frame)
                        self.messages_sent += 1
                        return True
                    self._write_outbox(payload)
                    return False
        except OSError:
            self.connected = False

        # Tactical continuity: queue unsent tracks so operators can replay once links recover.
        self._write_outbox(payload)
        return False

    def receive(self) -> Optional[str]:
        """Non-blocking receive from active transport."""
        if self.transport_type == "multicast" and self.multicast_socket is not None:
            try:
                data, _addr = self.multicast_socket.recvfrom(65535)
                if not data:
                    return None
                self.messages_received += 1
                return data.decode("utf-8", errors="ignore")
            except BlockingIOError:
                return None
            except OSError:
                self.connected = False
                return None

        if self.transport_type == "tak_server":
            if self.tak_socket is None and not self._reconnect_tak():
                return None
            try:
                assert self.tak_socket is not None
                chunk = self.tak_socket.recv(65535)
            except BlockingIOError:
                return None
            except OSError:
                self.connected = False
                return None

            if not chunk:
                self.connected = False
                return None

            self._tcp_buffer += chunk
            xml = self._extract_tcp_xml()
            if xml:
                self.messages_received += 1
            return xml
        return None

    def disconnect(self) -> None:
        """Cleanly close active sockets."""
        for sock in (self.multicast_socket, self.tak_socket):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self.multicast_socket = None
        self.tak_socket = None
        self.transport_type = None
        self.connected = False
        self._tcp_buffer = b""

    def health_check(self) -> dict:
        return {
            "connected": bool(self.connected),
            "transport_type": self.transport_type,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
        }

    @staticmethod
    def _load_config(config: dict | None) -> dict:
        defaults = {
            "multicast_address": "239.2.3.1",
            "multicast_port": 6969,
            "tak_server_url": None,
            "tak_protocol_version": 0,
            "outbox_dir": "data/interop/cot_outbox/",
        }
        source: dict[str, Any] = {}
        cfg_path = Path("configs/interop-extended.yaml")
        if cfg_path.exists():
            try:
                loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    source = loaded.get("cot", {}) if isinstance(loaded.get("cot"), dict) else {}
            except Exception:
                source = {}
        overrides = dict(config or {})
        if isinstance(overrides.get("cot"), dict):
            overrides = dict(overrides["cot"])
        return {**defaults, **source, **overrides}

    @staticmethod
    def _parse_tak_url(url: str) -> tuple[str, int]:
        raw = str(url).strip()
        parsed = urlparse(raw if "://" in raw else f"tcp://{raw}")
        host = str(parsed.hostname or "").strip()
        if not host:
            raise ValueError("TAK server URL missing hostname")
        port = int(parsed.port or 8087)
        if not (1 <= port <= 65535):
            raise ValueError("TAK server port out of range")
        return host, port

    def _reconnect_tak(self) -> bool:
        if not self.tak_server_url:
            return False
        try:
            host, port = self._parse_tak_url(self.tak_server_url)
            sock = socket.create_connection((host, port), timeout=2.5)
            sock.setblocking(False)
            if self.tak_socket is not None:
                try:
                    self.tak_socket.close()
                except OSError:
                    pass
            self.tak_socket = sock
            self.transport_type = "tak_server"
            self.connected = True
            return True
        except (OSError, ValueError):
            self.connected = False
            return False

    def _extract_tcp_xml(self) -> Optional[str]:
        data = self._tcp_buffer
        if data.startswith(self._TAK_V0_HEADER):
            data = data[len(self._TAK_V0_HEADER) :]

        start = data.find(b"<event")
        end = data.find(b"</event>")
        if start == -1 or end == -1 or end < start:
            self._tcp_buffer = data
            return None

        end_idx = end + len(b"</event>")
        xml = data[start:end_idx].decode("utf-8", errors="ignore")
        self._tcp_buffer = data[end_idx:]
        return xml

    def _write_outbox(self, xml: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        message_id = f"cot-{timestamp}-{uuid4().hex[:8]}"
        path = self.outbox_dir / f"{message_id}.xml"
        path.write_text(str(xml), encoding="utf-8")

