"""In-memory range network state loaded from a YAML scenario file."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class NetworkModel:
    """Mutable S1 range graph used by the mock XiiD MCP tools."""

    scenario_id: str
    stlinks: List[Dict[str, Any]]
    routes: List[Dict[str, Any]]
    hosts: List[Dict[str, Any]]
    sessions: List[Dict[str, Any]]
    vulnerabilities: List[Dict[str, Any]]
    audit_chain: List[Dict[str, Any]] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, repr=False)
    _snapshots: List[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_scenario(cls, path: Path) -> "NetworkModel":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("scenario file must be a mapping")
        return cls(
            scenario_id=str(raw.get("scenario_id", "unknown")),
            stlinks=[dict(item) for item in raw.get("stlinks", [])],
            routes=[dict(item) for item in raw.get("routes", [])],
            hosts=[dict(item) for item in raw.get("hosts", [])],
            sessions=[dict(item) for item in raw.get("sessions", [])],
            vulnerabilities=[dict(item) for item in raw.get("vulnerabilities", [])],
        )

    def snapshot(self) -> None:
        with self._lock:
            self._snapshots.append(
                json.dumps(
                    {
                        "stlinks": self.stlinks,
                        "routes": self.routes,
                        "hosts": self.hosts,
                        "sessions": self.sessions,
                    },
                    sort_keys=True,
                )
            )

    def rollback_last(self) -> bool:
        with self._lock:
            if not self._snapshots:
                return False
            payload = json.loads(self._snapshots.pop())
            self.stlinks = payload["stlinks"]
            self.routes = payload["routes"]
            self.hosts = payload["hosts"]
            self.sessions = payload["sessions"]
            return True

    def list_stlinks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.stlinks)

    def list_routes(self) -> List[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.routes)

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "scenario_id": self.scenario_id,
                "stlinks_active": sum(1 for s in self.stlinks if s.get("status") == "active"),
                "routes_active": sum(1 for r in self.routes if r.get("status") == "active"),
                "hosts_quarantined": sum(1 for h in self.hosts if h.get("quarantined")),
            }

    def verify_chain(self) -> Dict[str, Any]:
        with self._lock:
            return {"chain_length": len(self.audit_chain), "intact": True}

    def list_vulns(self) -> List[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.vulnerabilities)

    def find_route(self, route_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for route in self.routes:
                if route.get("id") == route_id:
                    return route
        return None

    def narrow_route(self, route_id: str, prefix: str) -> Dict[str, Any]:
        with self._lock:
            route = self.find_route(route_id)
            if route is None:
                raise ValueError(f"unknown route: {route_id}")
            route["narrow_to"] = prefix
            route["status"] = "narrowed"
            return copy.deepcopy(route)

    def expire_route(self, route_id: str) -> Dict[str, Any]:
        with self._lock:
            route = self.find_route(route_id)
            if route is None:
                raise ValueError(f"unknown route: {route_id}")
            route["status"] = "expired"
            return copy.deepcopy(route)

    def deploy_stlink(self, stlink_id: str, endpoint: str) -> Dict[str, Any]:
        with self._lock:
            for stlink in self.stlinks:
                if stlink.get("id") == stlink_id:
                    stlink["endpoint"] = endpoint
                    stlink["status"] = "active"
                    return copy.deepcopy(stlink)
            created = {"id": stlink_id, "endpoint": endpoint, "status": "active"}
            self.stlinks.append(created)
            return copy.deepcopy(created)

    def disable_stlink(self, stlink_id: str) -> Dict[str, Any]:
        with self._lock:
            for stlink in self.stlinks:
                if stlink.get("id") == stlink_id:
                    stlink["status"] = "disabled"
                    return copy.deepcopy(stlink)
        raise ValueError(f"unknown stlink: {stlink_id}")

    def terminate_session(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            for session in self.sessions:
                if session.get("id") == session_id:
                    session["active"] = False
                    return copy.deepcopy(session)
        raise ValueError(f"unknown session: {session_id}")

    def quarantine_host(self, host_id: str) -> Dict[str, Any]:
        with self._lock:
            for host in self.hosts:
                if host.get("id") == host_id:
                    host["quarantined"] = True
                    return copy.deepcopy(host)
        raise ValueError(f"unknown host: {host_id}")

    def append_audit(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self.audit_chain.append(dict(event))
