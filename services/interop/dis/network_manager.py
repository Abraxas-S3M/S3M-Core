"""DIS UDP networking manager with receive buffering and entity cache."""

from __future__ import annotations

from datetime import datetime, timezone
import socket
import threading
import time
from typing import Dict, List, Optional

from services.interop.dis.dead_reckoning import DISDeadReckoning
from services.interop.dis.pdu_factory import DISPDUFactory
from services.interop.models import DISEntityID, DISPDUType


class DISNetworkManager:
    """Handles UDP broadcast I/O and received entity state tracking."""

    def __init__(self, broadcast_address: str = "255.255.255.255", port: int = 3000, exercise_id: int = 1):
        self.broadcast_address = broadcast_address
        self.port = int(port)
        self.exercise_id = int(exercise_id)
        self.socket: Optional[socket.socket] = None
        self.running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._received_pdus: List[bytes] = []
        self._received_entities: Dict[tuple, dict] = {}
        self._last_entity_sent: Dict[tuple, dict] = {}
        self._factory = DISPDUFactory()
        self._dr = DISDeadReckoning()
        self._started_at: Optional[float] = None
        self._stats = {"pdus_sent": 0, "pdus_received": 0, "send_errors": 0, "recv_errors": 0}

    def start(self) -> bool:
        if self.running:
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.setblocking(False)
            self.socket = sock
            self.running = True
            self._started_at = time.time()
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True, name="dis-recv")
            self._recv_thread.start()
            return True
        except OSError:
            self.running = False
            self.socket = None
            return False

    def stop(self) -> None:
        self.running = False
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None

    def _recv_loop(self) -> None:
        while self.running:
            if self.socket is None:
                time.sleep(0.05)
                continue
            try:
                data, _addr = self.socket.recvfrom(65535)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            except OSError:
                if self.running:
                    self._stats["recv_errors"] += 1
                time.sleep(0.02)
                continue
            with self._lock:
                self._received_pdus.append(data)
                self._stats["pdus_received"] += 1
            try:
                if self._factory.identify_pdu_type(data) == DISPDUType.ENTITY_STATE:
                    decoded = self._factory.decode_entity_state(data)
                    ent_id = decoded["entity_id"]
                    key = ent_id.to_tuple() if isinstance(ent_id, DISEntityID) else tuple(ent_id)
                    decoded["_last_update"] = time.time()
                    self._received_entities[key] = decoded
            except Exception:
                continue

    def send_pdu(self, pdu_bytes: bytes) -> bool:
        if self.socket is None:
            return False
        try:
            self.socket.sendto(pdu_bytes, (self.broadcast_address, self.port))
            self._stats["pdus_sent"] += 1
            try:
                decoded = self._factory.decode_any(pdu_bytes)
                payload = decoded.get("data", {})
                ent = payload.get("entity_id")
                if isinstance(ent, DISEntityID):
                    self._last_entity_sent[ent.to_tuple()] = payload
            except Exception:
                pass
            return True
        except OSError:
            self._stats["send_errors"] += 1
            return False

    def receive_pdus(self, timeout: float = 0.1) -> List[bytes]:
        if timeout > 0:
            time.sleep(min(timeout, 0.25))
        with self._lock:
            rows = list(self._received_pdus)
            self._received_pdus.clear()
        return rows

    def get_received_entities(self) -> Dict[tuple, dict]:
        now = time.time()
        output: Dict[tuple, dict] = {}
        for key, state in list(self._received_entities.items()):
            dt = max(0.0, now - float(state.get("_last_update", now)))
            extrapolated = self._dr.extrapolate(state, dt, algorithm=int(state.get("dead_reckoning_algorithm", 2)))
            output[key] = extrapolated
        return output

    def get_exercise_stats(self) -> dict:
        active_time = 0.0
        if self._started_at is not None:
            active_time = max(0.0, time.time() - self._started_at)
        return {
            "exercise_id": self.exercise_id,
            "pdus_sent": self._stats["pdus_sent"],
            "pdus_received": self._stats["pdus_received"],
            "send_errors": self._stats["send_errors"],
            "recv_errors": self._stats["recv_errors"],
            "entity_count": len(self._received_entities),
            "active_seconds": round(active_time, 3),
        }

    def health_check(self) -> dict:
        return {
            "status": "operational" if self.running else "stopped",
            "socket_bound": self.socket is not None,
            "port": self.port,
            "broadcast_address": self.broadcast_address,
            "stats": self.get_exercise_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
