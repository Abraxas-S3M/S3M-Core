"""Canary deployment for adversarial resilience testing in S3M.

Military/tactical context:
Canaries emulate sensitive mission artifacts so red-team style probing inside a
container is detected early, before real credentials or operational plans are
touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import socket
import threading
from typing import Callable, Dict, List, Mapping, Sequence


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class Canary:
    """One planted honey artifact that should never be touched."""

    canary_id: str
    type: str
    location: str
    token: str
    alert_on_access: bool = True


@dataclass(frozen=True, slots=True)
class CanaryTrip:
    """Represents one detected interaction with a canary artifact."""

    canary_id: str
    accessed_at: str
    accessed_by: str
    method: str


class CanaryDeployer:
    """Plant honeypot artifacts and report canary trips."""

    def __init__(
        self,
        canary_root: str | Path = "/tmp/s3m_canaries",
        token_observer: Callable[[set[str]], Sequence[Mapping[str, str]]] | None = None,
    ) -> None:
        self._canary_root = Path(canary_root)
        self._token_observer = token_observer
        self._deployed: Dict[str, Canary] = {}
        self._trips: List[CanaryTrip] = []
        self._trip_keys: set[tuple[str, str, str, str]] = set()
        self._honeypot_sockets: List[socket.socket] = []
        self._honeypot_threads: List[threading.Thread] = []
        self._honeypot_stop = threading.Event()
        self._trip_lock = threading.Lock()

    def deploy_canaries(self, container_id: str) -> List[Canary]:
        """Deploy credential, filesystem, network, and environment canaries."""

        if not isinstance(container_id, str) or not container_id.strip():
            raise ValueError("container_id must be a non-empty string")
        normalized_container = container_id.strip()
        deployment_root = self._canary_root / self._sanitize_container_id(normalized_container)
        deployment_root.mkdir(parents=True, exist_ok=True)

        self.shutdown()
        self._deployed.clear()

        deployed = [
            self._deploy_fake_credentials(deployment_root, normalized_container),
            self._deploy_fake_ssh_key(deployment_root, normalized_container),
            self._deploy_fake_db_connection(deployment_root, normalized_container),
            self._deploy_honeypot_service(normalized_container),
            self._deploy_fake_git_repository(deployment_root, normalized_container),
            self._deploy_environment_token(normalized_container),
        ]
        self._deployed = {canary.canary_id: canary for canary in deployed}
        return deployed

    def check_canaries(self) -> List[CanaryTrip]:
        """Return all known canary trip events."""

        self._collect_observed_token_events()
        with self._trip_lock:
            return list(sorted(self._trips, key=lambda item: item.accessed_at))

    def shutdown(self) -> None:
        """Stop any running honeypot services."""

        self._honeypot_stop.set()
        for sock in self._honeypot_sockets:
            try:
                sock.close()
            except OSError:
                pass
        for thread in self._honeypot_threads:
            thread.join(timeout=0.5)
        self._honeypot_threads.clear()
        self._honeypot_sockets.clear()
        self._honeypot_stop = threading.Event()

    def _deploy_fake_credentials(self, root: Path, container_id: str) -> Canary:
        canary = self._new_canary(
            canary_type="fake_credentials_file",
            location=str(root / "home" / ".aws" / "credentials_backup"),
            container_id=container_id,
        )
        content = (
            "[default]\n"
            f"aws_access_key_id = AKIA{canary.token[:16].upper()}\n"
            f"aws_secret_access_key = {canary.token}\n"
        )
        self._write_file(Path(canary.location), content)
        return canary

    def _deploy_fake_ssh_key(self, root: Path, container_id: str) -> Canary:
        canary = self._new_canary(
            canary_type="fake_ssh_key",
            location=str(root / "home" / ".ssh" / "id_rsa_archive.bak"),
            container_id=container_id,
        )
        content = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            f"{canary.token}\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        )
        self._write_file(Path(canary.location), content)
        return canary

    def _deploy_fake_db_connection(self, root: Path, container_id: str) -> Canary:
        canary = self._new_canary(
            canary_type="fake_db_config",
            location=str(root / "etc" / "mission" / "database.conf"),
            container_id=container_id,
        )
        content = (
            "[database]\n"
            f"dsn = postgresql://canary_user:{canary.token}@vault-db.internal:5432/mission\n"
        )
        self._write_file(Path(canary.location), content)
        return canary

    def _deploy_honeypot_service(self, container_id: str) -> Canary:
        service_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        service_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        service_socket.bind(("127.0.0.1", 0))
        service_socket.listen(5)
        service_socket.settimeout(0.2)
        host, port = service_socket.getsockname()

        canary = self._new_canary(
            canary_type="honeypot_service",
            location=f"{host}:{port}",
            container_id=container_id,
        )
        listener = threading.Thread(
            target=self._honeypot_listener,
            args=(service_socket, canary),
            daemon=True,
            name=f"s3m-canary-{canary.canary_id}",
        )
        listener.start()
        self._honeypot_sockets.append(service_socket)
        self._honeypot_threads.append(listener)
        return canary

    def _deploy_fake_git_repository(self, root: Path, container_id: str) -> Canary:
        repository_root = root / "opt" / "sensitive-research"
        canary = self._new_canary(
            canary_type="fake_git_repository",
            location=str(repository_root),
            container_id=container_id,
        )
        self._write_file(
            repository_root / ".git" / "config",
            "[core]\nrepositoryformatversion = 0\nbare = false\n",
        )
        self._write_file(
            repository_root / "README.md",
            (
                "# Sensitive Logistics Snapshot\n\n"
                "This repository is a defensive canary.\n"
                f"canary_token={canary.token}\n"
            ),
        )
        return canary

    def _deploy_environment_token(self, container_id: str) -> Canary:
        canary = self._new_canary(
            canary_type="environment_variable",
            location=f"S3M_CANARY_{container_id.upper()}",
            container_id=container_id,
        )
        os.environ[canary.location] = canary.token
        return canary

    def _new_canary(self, canary_type: str, location: str, container_id: str) -> Canary:
        sequence = len(self._deployed) + 1
        canary_id = f"{container_id}-{canary_type}-{sequence:02d}"
        token = f"s3m_canary_{secrets.token_hex(16)}"
        return Canary(
            canary_id=canary_id,
            type=canary_type,
            location=location,
            token=token,
            alert_on_access=True,
        )

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _honeypot_listener(self, service_socket: socket.socket, canary: Canary) -> None:
        while not self._honeypot_stop.is_set():
            try:
                conn, addr = service_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return

            with conn:
                self._record_trip(
                    CanaryTrip(
                        canary_id=canary.canary_id,
                        accessed_at=_utc_now_iso(),
                        accessed_by=f"{addr[0]}:{addr[1]}",
                        method="network_connect",
                    )
                )
                try:
                    conn.sendall(f"S3M_CANARY_TOKEN={canary.token}\n".encode("utf-8"))
                except OSError:
                    pass

    def _collect_observed_token_events(self) -> None:
        if self._token_observer is None or not self._deployed:
            return

        deployed_by_token = {canary.token: canary for canary in self._deployed.values()}
        events = self._token_observer(set(deployed_by_token.keys()))
        for event in events:
            token = event.get("token", "")
            canary = deployed_by_token.get(token)
            if canary is None:
                continue
            self._record_trip(
                CanaryTrip(
                    canary_id=canary.canary_id,
                    accessed_at=event.get("accessed_at", _utc_now_iso()),
                    accessed_by=event.get("accessed_by", "unknown"),
                    method=event.get("method", "token_observed"),
                )
            )

    def _record_trip(self, trip: CanaryTrip) -> None:
        key = (trip.canary_id, trip.accessed_at, trip.accessed_by, trip.method)
        with self._trip_lock:
            if key in self._trip_keys:
                return
            self._trip_keys.add(key)
            self._trips.append(trip)

    def _sanitize_container_id(self, container_id: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in container_id)
        return cleaned.strip("_") or "container"

    def __del__(self) -> None:  # pragma: no cover - cleanup guard
        self.shutdown()
