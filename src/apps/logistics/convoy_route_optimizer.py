"""Threat-aware convoy route optimization for logistics missions."""

from __future__ import annotations

import math
import uuid
from typing import Dict, List, Optional, Tuple

from src.apps._shared import clamp, ensure_non_empty_text, normalize_coords, safe_float, utc_now_iso
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest
from src.threat_detection.threat_manager import ThreatManager

Point3 = Tuple[float, float, float]


class ConvoyRouteOptimizer:
    """Optimize convoy paths with tactical threat standoff handling."""

    _LEVEL_RADIUS = {"CRITICAL": 100.0, "HIGH": 75.0, "MEDIUM": 50.0}
    _LEVEL_WEIGHT = {"CRITICAL": 1.0, "HIGH": 0.7, "MEDIUM": 0.45}

    def __init__(self) -> None:
        self._orchestrator = Orchestrator()
        self._threat_manager = ThreatManager()
        self._routes: Dict[str, dict] = {}
        self._reopt_map: Dict[str, dict] = {}

    def _norm_threats(self, threats: List[dict]) -> List[dict]:
        out: List[dict] = []
        for threat in threats:
            pos_raw = threat.get("position") or threat.get("location") or (0.0, 0.0, 0.0)
            pos = normalize_coords(pos_raw, dims=3, default=(0.0, 0.0, 0.0))
            level = str(threat.get("level", "MEDIUM")).upper()
            if level not in self._LEVEL_RADIUS:
                level = "MEDIUM"
            out.append(
                {
                    "id": threat.get("id", f"thr-{len(out)+1}"),
                    "position": pos,
                    "level": level,
                    "radius": safe_float(threat.get("radius"), self._LEVEL_RADIUS[level]),
                    "weight": self._LEVEL_WEIGHT[level],
                }
            )
        return out

    def _pull_threats(self) -> List[dict]:
        events = self._threat_manager.get_threats(limit=250)
        out: List[dict] = []
        for event in events:
            level_name = event.level.name
            if level_name not in {"MEDIUM", "HIGH", "CRITICAL"}:
                continue
            loc = event.location or {}
            x = loc.get("x", loc.get("lon", 0.0))
            y = loc.get("y", loc.get("lat", 0.0))
            z = loc.get("z", 0.0)
            out.append(
                {
                    "id": event.event_id,
                    "position": (safe_float(x), safe_float(y), safe_float(z)),
                    "level": level_name,
                }
            )
        return out

    @staticmethod
    def _dist(a: Point3, b: Point3) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    def _line_point_distance(self, a: Point3, b: Point3, p: Point3) -> float:
        ax, ay, az = a
        bx, by, bz = b
        px, py, pz = p
        ab = (bx - ax, by - ay, bz - az)
        ap = (px - ax, py - ay, pz - az)
        ab2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
        if ab2 <= 1e-6:
            return self._dist(a, p)
        t = clamp((ab[0] * ap[0] + ab[1] * ap[1] + ab[2] * ap[2]) / ab2, 0.0, 1.0)
        q = (ax + t * ab[0], ay + t * ab[1], az + t * ab[2])
        return self._dist(q, p)

    def _avoidance_path(self, origin: Point3, destination: Point3, threats: List[dict], multiplier: float = 1.0) -> List[Point3]:
        waypoints: List[Point3] = [origin]
        vector = (destination[0] - origin[0], destination[1] - origin[1], destination[2] - origin[2])
        vec_norm = max(1.0, math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2))
        perp = (-vector[1] / vec_norm, vector[0] / vec_norm, 0.0)
        for threat in threats:
            threat_pos = normalize_coords(threat.get("position"), dims=3, default=(0.0, 0.0, 0.0))
            radial = safe_float(threat.get("radius"), 50.0) * multiplier
            dline = self._line_point_distance(origin, destination, threat_pos)
            if dline < radial:
                offset = radial - dline + 20.0
                side = 1.0 if threat_pos[1] >= (origin[1] + destination[1]) / 2 else -1.0
                wp = (
                    threat_pos[0] + perp[0] * side * offset,
                    threat_pos[1] + perp[1] * side * offset,
                    origin[2],
                )
                waypoints.append(wp)
        waypoints.append(destination)
        return waypoints

    def _path_distance(self, path: List[Point3]) -> float:
        if len(path) < 2:
            return 0.0
        return sum(self._dist(path[idx], path[idx + 1]) for idx in range(len(path) - 1))

    def _metrics(self, path: List[Point3], threats: List[dict]) -> dict:
        distance = self._path_distance(path)
        speed_mps = 12.0
        eta = distance / speed_mps if speed_mps > 0 else distance
        nearby = 0
        risk_acc = 0.0
        for threat in threats:
            tpos = normalize_coords(threat.get("position"), dims=3, default=(0.0, 0.0, 0.0))
            min_d = min(self._line_point_distance(path[i], path[i + 1], tpos) for i in range(len(path) - 1))
            if min_d <= 200.0:
                nearby += 1
            radius = safe_float(threat.get("radius"), 50.0)
            weight = safe_float(threat.get("weight"), 0.45)
            risk_acc += weight * clamp((radius + 200.0 - min_d) / (radius + 200.0), 0.0, 1.0)
        max_norm = max(1.0, len(threats))
        risk_score = clamp(risk_acc / max_norm, 0.0, 1.0)
        return {
            "path": path,
            "distance_m": round(distance, 2),
            "estimated_time_s": round(eta, 2),
            "risk_score": round(risk_score, 4),
            "threats_nearby": nearby,
        }

    def _llm_recommendation(self, brief: str) -> str:
        try:
            response = self._orchestrator.process(QueryRequest(prompt=brief, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "")
            if isinstance(text, str) and text.strip() and "pending" not in text.lower():
                return text.strip()
        except Exception:
            pass
        return "Template recommendation: select the route with lower risk score unless mission urgency requires shorter travel time."

    def optimize_route(
        self,
        origin: tuple,
        destination: tuple,
        threat_overlay: Optional[List[dict]] = None,
        platform_type: str = "ground_wheeled",
    ) -> dict:
        """Generate primary and alternative convoy routes against threat overlay."""
        origin_pt = normalize_coords(origin, dims=3, default=(0.0, 0.0, 0.0))
        dest_pt = normalize_coords(destination, dims=3, default=(1000.0, 1000.0, 0.0))
        ensure_non_empty_text(platform_type, "platform_type")
        threats = self._norm_threats(threat_overlay if threat_overlay is not None else self._pull_threats())
        primary_path = self._avoidance_path(origin_pt, dest_pt, threats, multiplier=1.0)
        primary = self._metrics(primary_path, threats)

        alternative = None
        if primary["risk_score"] > 0.5:
            alt_path = self._avoidance_path(origin_pt, dest_pt, threats, multiplier=1.5)
            alternative = self._metrics(alt_path, threats)

        route_id = str(uuid.uuid4())
        chosen = "primary"
        if alternative and alternative["risk_score"] + 0.05 < primary["risk_score"]:
            chosen = "alternative"

        recommendation = self._llm_recommendation(
            "Compare convoy routes and recommend one. "
            f"Primary={primary}. Alternative={alternative}. Mission=threat-aware logistics movement."
        )
        threat_summary = (
            f"{len(threats)} threats considered; {primary['threats_nearby']} within 200m of primary route. "
            f"Recommended route: {chosen}."
        )
        result = {
            "route_id": route_id,
            "primary_route": primary,
            "alternative_route": alternative,
            "recommendation": recommendation,
            "threat_summary": threat_summary,
            "timestamp": utc_now_iso(),
        }
        self._routes[route_id] = {
            "origin": origin_pt,
            "destination": dest_pt,
            "platform_type": platform_type,
            "result": result,
        }
        return result

    def reoptimize(self, route_id: str, new_threats: List[dict]) -> dict:
        """Re-run optimization with updated threat intelligence overlay."""
        ensure_non_empty_text(route_id, "route_id")
        if route_id not in self._routes:
            raise ValueError(f"unknown route_id: {route_id}")
        base = self._routes[route_id]
        updated = self.optimize_route(
            origin=base["origin"],
            destination=base["destination"],
            threat_overlay=new_threats,
            platform_type=base["platform_type"],
        )
        self._reopt_map[route_id] = updated
        return updated

