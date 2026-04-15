"""JREAP-C UDP bridge for ingesting Link 16 J-series tracks into S3M."""

from __future__ import annotations

from datetime import datetime, timezone
import socket
import threading
import time
from typing import Any, Dict, List, Optional

from services.interop.jreap.jreap_handler import JREAPHandler


class JREAPBridge:
    """Receives JREAP-C packets, decodes tracks, and crossfeeds interop outputs."""

    def __init__(self, config: dict):
        raw_config = config or {}
        self.config = raw_config.get("jreap", raw_config)
        self.listen_port = int(self.config.get("listen_port", 5555))
        self.supported_j_series = list(
            self.config.get("supported_j_series", ["J2.2", "J3.2", "J3.5", "J13.2"])
        )
        self.handler = JREAPHandler(self.config)

        self.socket: Optional[socket.socket] = None
        self.running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._received_packets: List[bytes] = []
        self._track_cache: Dict[str, dict] = {}
        self._started_at: Optional[float] = None
        self._stats = {
            "packets_received": 0,
            "parse_errors": 0,
            "tracks_decoded": 0,
            "cot_forwarded": 0,
            "dis_forwarded": 0,
            "recv_errors": 0,
        }

    def start_listener(self, port: int) -> bool:
        if self.running:
            return True
        self.listen_port = int(port or self.listen_port)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.listen_port))
            sock.setblocking(False)
            self.socket = sock
            self.running = True
            self._started_at = time.time()
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True, name="jreap-recv")
            self._recv_thread.start()
            return True
        except OSError:
            self.running = False
            self.socket = None
            return False

    def stop_listener(self) -> None:
        self.running = False
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None

    def process_received(self) -> List[dict]:
        with self._lock:
            packets = list(self._received_packets)
            self._received_packets.clear()
        decoded_tracks: List[dict] = []
        for packet in packets:
            try:
                header = self.handler.parse_jreap_header(packet)
            except ValueError:
                self._stats["parse_errors"] += 1
                continue
            payload_end = self.handler.HEADER_SIZE + int(header["payload_length"])
            if len(packet) < payload_end:
                self._stats["parse_errors"] += 1
                continue
            payload = packet[self.handler.HEADER_SIZE : payload_end]
            rows = self._decode_payload(header=header, payload=payload)
            for row in rows:
                row["source"] = "jreap-c"
                row["jreap_sequence"] = int(header["sequence_number"])
                row["jreap_timestamp_us"] = int(header["timestamp_us"])
                track_id = str(row.get("id", f"track-{len(self._track_cache) + 1}"))
                self._track_cache[track_id] = row
                decoded_tracks.append(row)
        self._stats["tracks_decoded"] += len(decoded_tracks)
        return decoded_tracks

    def get_air_tracks(self) -> List[dict]:
        return [track for track in self.get_tracks() if str(track.get("domain", "")).lower() == "air"]

    def get_surface_tracks(self) -> List[dict]:
        return [track for track in self.get_tracks() if str(track.get("domain", "")).lower() == "surface"]

    def crossfeed_to_cot(self, cot_bridge) -> int:
        tracks = self.process_received()
        if not tracks:
            tracks = self.get_tracks()
        forwarded = 0
        for track in tracks:
            event = self._track_to_cot_event(track)
            if self._send_cot_event(cot_bridge, event):
                forwarded += 1
        self._stats["cot_forwarded"] += forwarded
        return forwarded

    def crossfeed_to_dis(self, dis_engine) -> int:
        tracks = self.process_received()
        if not tracks:
            tracks = self.get_tracks()
        forwarded = 0
        for track in tracks:
            entity = self._track_to_dis_entity(track)
            sent = False
            if hasattr(dis_engine, "publish_entity"):
                sent = bool(dis_engine.publish_entity(entity))
            elif hasattr(dis_engine, "send_entity"):
                sent = bool(dis_engine.send_entity(entity))
            if sent:
                forwarded += 1
        self._stats["dis_forwarded"] += forwarded
        return forwarded

    def health_check(self) -> dict:
        uptime = 0.0 if self._started_at is None else max(0.0, time.time() - self._started_at)
        return {
            "status": "operational" if self.running else "stopped",
            "listener_port": self.listen_port,
            "socket_bound": self.socket is not None,
            "supported_j_series": list(self.supported_j_series),
            "track_count": len(self._track_cache),
            "stats": self.get_stats(),
            "uptime_seconds": round(uptime, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_tracks(self) -> List[dict]:
        return list(self._track_cache.values())

    def get_stats(self) -> dict:
        return {
            "packets_received": int(self._stats["packets_received"]),
            "parse_errors": int(self._stats["parse_errors"]),
            "tracks_decoded": int(self._stats["tracks_decoded"]),
            "cot_forwarded": int(self._stats["cot_forwarded"]),
            "dis_forwarded": int(self._stats["dis_forwarded"]),
            "recv_errors": int(self._stats["recv_errors"]),
            "cache_size": len(self._track_cache),
        }

    def _recv_loop(self) -> None:
        while self.running:
            if self.socket is None:
                time.sleep(0.05)
                continue
            try:
                packet, _addr = self.socket.recvfrom(65535)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            except OSError:
                if self.running:
                    self._stats["recv_errors"] += 1
                time.sleep(0.02)
                continue
            with self._lock:
                self._received_packets.append(packet)
                self._stats["packets_received"] += 1

    def _decode_payload(self, header: dict, payload: bytes) -> List[dict]:
        if int(header.get("message_type", 0)) != 1:
            return []
        # Tactical context: mixed payload support allows coalition gateways to
        # bundle multiple J-series records into one UDP datagram on constrained links.
        rows = self.handler.parse_j_series(payload, "mixed")
        if rows:
            return self._filter_supported(rows)
        for series in self.supported_j_series:
            parsed = self.handler.parse_j_series(payload, series)
            if parsed:
                return self._filter_supported(parsed)
        return []

    def _filter_supported(self, tracks: List[dict]) -> List[dict]:
        supported = {str(code).upper() for code in self.supported_j_series}
        if not supported:
            return tracks
        return [track for track in tracks if str(track.get("j_series", "")).upper() in supported]

    @staticmethod
    def _track_to_cot_event(track: dict) -> Dict[str, Any]:
        return {
            "uid": str(track.get("id", "jreap-track")),
            "type": f"jreap/{track.get('domain', 'unknown')}",
            "time": datetime.now(timezone.utc).isoformat(),
            "lat": track.get("latitude"),
            "lon": track.get("longitude"),
            "hae": track.get("altitude"),
            "track": {
                "speed": track.get("speed"),
                "course": track.get("heading"),
                "summary": track.get("summary"),
            },
            "source": "JREAP-C",
        }

    @staticmethod
    def _send_cot_event(cot_bridge: Any, event: dict) -> bool:
        if hasattr(cot_bridge, "publish_event"):
            return bool(cot_bridge.publish_event(event))
        if hasattr(cot_bridge, "send_event"):
            return bool(cot_bridge.send_event(event))
        if hasattr(cot_bridge, "ingest_track"):
            return bool(cot_bridge.ingest_track(event))
        if hasattr(cot_bridge, "emit"):
            return bool(cot_bridge.emit(event))
        if callable(cot_bridge):
            return bool(cot_bridge(event))
        return False

    @staticmethod
    def _track_to_dis_entity(track: dict) -> Dict[str, Any]:
        domain = str(track.get("domain", "")).lower()
        dis_domain = {"air": 2, "surface": 3, "land": 1}.get(domain, 1)
        return {
            "entity_id": str(track.get("id", "jreap-entity")),
            "name": str(track.get("summary", "JREAP track")),
            "affiliation": "unknown",
            "entity_type": {
                "kind": 1,
                "domain": dis_domain,
                "country": 178,
                "category": 1,
                "subcategory": 0,
                "specific": 0,
                "extra": 0,
            },
            "position": {
                "lat": float(track.get("latitude") or 0.0),
                "lon": float(track.get("longitude") or 0.0),
                "alt": float(track.get("altitude") or 0.0),
            },
            "orientation": {"heading": float(track.get("heading") or 0.0)},
            "velocity": {"x": float(track.get("speed") or 0.0), "y": 0.0, "z": 0.0},
            "marking": str(track.get("id", "JREAP")),
        }
