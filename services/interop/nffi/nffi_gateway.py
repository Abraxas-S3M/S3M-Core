"""NFFI transport gateway for coalition blue-force interoperability."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
from typing import List, Optional
from uuid import uuid4

from services.interop.nffi.nffi_message import NFFIMessageBuilder


class NFFIGateway:
    """Transmit and receive NFFI tracks across STANAG 5527 transport profiles."""

    def __init__(self, config: dict, message_builder: NFFIMessageBuilder):
        cfg = dict(config or {})
        self.config = cfg
        self.message_builder = message_builder
        self.transport_profile = str(cfg.get("transport_profile", "IP-1")).upper()
        self.gateway_url = cfg.get("gateway_url")
        self.publish_interval_seconds = int(cfg.get("publish_interval_seconds", 10))
        self.track_source_country = str(cfg.get("track_source_country", "SAU")).upper()
        self.system_id = str(cfg.get("system_id", "S3M-FALCON"))
        self.stale_threshold_seconds = int(cfg.get("stale_threshold_seconds", 300))
        self.multicast_group = str(cfg.get("multicast_group", "239.2.3.1"))
        self.multicast_port = int(cfg.get("multicast_port", 4571))

        self.outbox_dir = Path(str(cfg.get("outbox_dir", "data/interop/nffi_outbox/")))
        self.inbox_dir = Path(str(cfg.get("inbox_dir", "data/interop/nffi_inbox/")))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        self.connected = False
        self.last_error: str | None = None
        self._tcp_socket: Optional[socket.socket] = None
        self._udp_send_socket: Optional[socket.socket] = None
        self._udp_recv_socket: Optional[socket.socket] = None

    def connect(self, gateway_url: str = None) -> bool:
        if gateway_url is not None:
            self.gateway_url = gateway_url
        self.disconnect()
        self.last_error = None

        profile = self.transport_profile
        if profile == "IP-1":
            if not self.gateway_url:
                self.connected = False
                return False
            try:
                host, port = self._parse_host_port(self.gateway_url)
                self._tcp_socket = socket.create_connection((host, port), timeout=2.0)
                self._tcp_socket.settimeout(0.2)
                self.connected = True
                return True
            except (OSError, ValueError) as exc:
                self.last_error = str(exc)
                self.connected = False
                return False

        if profile == "IP-2":
            try:
                self._udp_send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                self._udp_send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                self._udp_recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                self._udp_recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._udp_recv_socket.bind(("", self.multicast_port))
                mreq = socket.inet_aton(self.multicast_group) + socket.inet_aton("0.0.0.0")
                self._udp_recv_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                self._udp_recv_socket.settimeout(0.2)
                self.connected = True
                return True
            except OSError as exc:
                self.last_error = str(exc)
                self.disconnect()
                return False

        self.connected = False
        return False

    def publish_friendly_tracks(self, tracks: List[dict]) -> int:
        xml = self.message_builder.build_message(
            tracks=tracks,
            country_iso3=self.track_source_country,
            system_id=self.system_id,
        )
        sent_count = len(self.message_builder.parse_message(xml))
        if sent_count == 0:
            return 0

        encoded = xml.encode("utf-8")
        profile = self.transport_profile
        if profile == "IP-1" and self.connected and self._tcp_socket is not None:
            try:
                self._tcp_socket.sendall(encoded + b"\n")
                return sent_count
            except OSError as exc:
                self.last_error = str(exc)
                self.connected = False

        if profile == "IP-2" and self.connected and self._udp_send_socket is not None:
            try:
                self._udp_send_socket.sendto(encoded, (self.multicast_group, self.multicast_port))
                return sent_count
            except OSError as exc:
                self.last_error = str(exc)
                self.connected = False

        self._write_outbox(xml)
        return sent_count

    def receive_coalition_tracks(self) -> List[dict]:
        payloads: List[str] = []
        profile = self.transport_profile
        if profile == "IP-1" and self.connected and self._tcp_socket is not None:
            msg = self._recv_tcp_payload()
            if msg:
                payloads.append(msg)
        elif profile == "IP-2" and self.connected and self._udp_recv_socket is not None:
            msg = self._recv_udp_payload()
            if msg:
                payloads.append(msg)

        if not payloads:
            payloads.extend(self._load_offline_inbox())

        tracks: List[dict] = []
        for xml in payloads:
            try:
                tracks.extend(self.message_builder.parse_message(xml))
            except Exception as exc:
                self.last_error = str(exc)
        return tracks

    def disconnect(self):
        self.connected = False
        for sock in (self._tcp_socket, self._udp_send_socket, self._udp_recv_socket):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._tcp_socket = None
        self._udp_send_socket = None
        self._udp_recv_socket = None

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "transport_profile": self.transport_profile,
            "connected": self.connected,
            "gateway_url": self.gateway_url,
            "publish_interval_seconds": self.publish_interval_seconds,
            "track_source_country": self.track_source_country,
            "system_id": self.system_id,
            "stale_threshold_seconds": self.stale_threshold_seconds,
            "offline_outbox_count": len(list(self.outbox_dir.glob("*.json"))),
            "offline_inbox_count": len(list(self.inbox_dir.glob("*.xml"))) + len(list(self.inbox_dir.glob("*.json"))),
            "last_error": self.last_error,
        }

    def _write_outbox(self, xml: str) -> dict:
        message_id = f"nffi-{uuid4().hex[:10]}"
        payload = {
            "message_id": message_id,
            "message_type": "NFFI_TRACK",
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "xml": xml,
        }
        path = self.outbox_dir / f"{message_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def _recv_tcp_payload(self) -> str:
        assert self._tcp_socket is not None
        try:
            data = self._tcp_socket.recv(131072)
            return data.decode("utf-8", errors="ignore").strip()
        except TimeoutError:
            return ""
        except OSError as exc:
            self.last_error = str(exc)
            self.connected = False
            return ""

    def _recv_udp_payload(self) -> str:
        assert self._udp_recv_socket is not None
        try:
            data, _ = self._udp_recv_socket.recvfrom(131072)
            return data.decode("utf-8", errors="ignore").strip()
        except TimeoutError:
            return ""
        except OSError as exc:
            self.last_error = str(exc)
            self.connected = False
            return ""

    def _load_offline_inbox(self) -> List[str]:
        payloads: List[str] = []
        for path in sorted(self.inbox_dir.glob("*.xml")):
            payloads.append(path.read_text(encoding="utf-8"))
        for path in sorted(self.inbox_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict) and isinstance(raw.get("xml"), str):
                payloads.append(raw["xml"])
        return payloads

    @staticmethod
    def _parse_host_port(gateway_url: str) -> tuple[str, int]:
        raw = str(gateway_url or "").strip()
        if not raw:
            raise ValueError("gateway_url is required for IP-1")
        # Tactical deployments may provide host:port or tcp://host:port.
        if "://" in raw:
            _, rest = raw.split("://", 1)
        else:
            rest = raw
        host_port = rest.split("/", 1)[0]
        if ":" not in host_port:
            raise ValueError("gateway_url must include port, e.g. 10.0.0.2:4571")
        host, port_str = host_port.rsplit(":", 1)
        return host.strip(), int(port_str)
