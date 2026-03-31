"""FastAPI routes for S3M Phase 8 navigation and edge inference."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from src.api.navigation_models import (
    CollisionCheckResponse,
    EdgeModelResponse,
    InferenceResultResponse,
    JetsonStatsResponse,
    NavigationStatusResponse,
    NavStateResponse,
    OptimizeModelRequest,
    PathResponse,
    PlanPathRequest,
    PlanWaypointsRequest,
    PoseResponse,
    PredictRequest,
    ReplanRequest,
    TrajectoryResponse,
    UpdateNavRequest,
)
from src.navigation.edge_inference.edge_llm_runner import EdgeLLMRunner
from src.navigation.edge_inference.inference_engine import EdgeInferenceEngine
from src.navigation.edge_inference.jetson_monitor import JetsonMonitor
from src.navigation.edge_inference.model_optimizer import ModelOptimizer
from src.navigation.localization.localization_manager import LocalizationManager
from src.navigation.models import Path, PathStatus, PlannerType, PlatformType
from src.navigation.planning.planning_manager import PlanningManager
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer

LOGGER = logging.getLogger(__name__)

navigation_router = APIRouter()

_localization = LocalizationManager()
_planning = PlanningManager()
_optimizer = ModelOptimizer()
_inference = EdgeInferenceEngine()
_edge_llm = EdgeLLMRunner()
_jetson = JetsonMonitor()
_audit_log: List[Dict[str, Any]] = []


def _audit(action: str, details: Dict[str, Any]) -> None:
    _audit_log.append({"action": action, "details": details})
    if len(_audit_log) > 1000:
        del _audit_log[:-1000]


def _path_response(path: Path) -> PathResponse:
    return PathResponse(**path.to_dict())


def _trajectory_response(traj) -> TrajectoryResponse:
    return TrajectoryResponse(**traj.to_dict())


@navigation_router.get("/navigation/status", response_model=NavigationStatusResponse)
async def navigation_status() -> NavigationStatusResponse:
    """Returns full Layer 05 status for tactical command health monitoring."""
    try:
        loc_state = _localization.get_state()
        planning_health = _planning.health_check()
        edge_status = _inference.health_check()
        jetson_stats = _jetson.get_stats()
        return NavigationStatusResponse(
            localization=loc_state.to_dict(),
            planning=planning_health,
            edge_inference=edge_status,
            jetson=jetson_stats.to_dict(),
            active_plans=_planning.get_active_plans(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@navigation_router.get("/navigation/pose", response_model=PoseResponse)
async def get_pose() -> PoseResponse:
    state = _localization.get_state()
    return PoseResponse(**state.pose.to_dict())


@navigation_router.get("/navigation/pose/history")
async def get_pose_history(limit: int = Query(default=50, ge=1, le=1000)) -> Dict[str, Any]:
    history = _localization.get_pose_history(limit=limit)
    return {"poses": [PoseResponse(**p.to_dict()).model_dump() for p in history], "total": len(history)}


@navigation_router.get("/navigation/gps/status")
async def gps_status() -> Dict[str, Any]:
    gps = _localization.get_state().gps_status
    return gps.to_dict()


@navigation_router.post("/navigation/localization/reset")
async def reset_localization(payload: Dict[str, Any]) -> Dict[str, Any]:
    pos = payload.get("position")
    if not isinstance(pos, (list, tuple)) or len(pos) != 3:
        raise HTTPException(status_code=400, detail="position must be [x, y, z]")
    _localization.reset((float(pos[0]), float(pos[1]), float(pos[2])))
    _audit("localization_reset", {"position": pos})
    return {"status": "ok"}


@navigation_router.post("/navigation/plan")
async def plan_path(req: PlanPathRequest) -> Dict[str, Any]:
    try:
        result = _planning.plan_route(
            start=req.start,
            goal=req.goal,
            obstacles=req.obstacles,
            planner_type=req.planner_type,
            platform_type=req.platform_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("plan_path", {"plan_id": result["plan_id"]})
    return {
        "plan_id": result["plan_id"],
        "path": _path_response(result["path"]).model_dump(),
        "trajectory": _trajectory_response(result["trajectory"]).model_dump(),
        "collision_check": result["collision_check"],
    }


@navigation_router.post("/navigation/plan/waypoints")
async def plan_waypoints(req: PlanWaypointsRequest) -> Dict[str, Any]:
    waypoint_payload = [wp.model_dump() for wp in req.waypoints]
    try:
        nav_plan_id = _planning.plan_waypoint_mission(waypoint_payload, platform_type=req.platform_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("plan_waypoints", {"plan_id": nav_plan_id})
    return {"plan_id": nav_plan_id}


@navigation_router.get("/navigation/plan/{plan_id}")
async def get_plan(plan_id: str) -> Dict[str, Any]:
    plan = _planning.active_plans.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    path = plan.get("path")
    traj = plan.get("trajectory")
    return {
        "plan_id": plan_id,
        "path": _path_response(path).model_dump() if path is not None else None,
        "trajectory": _trajectory_response(traj).model_dump() if traj is not None else None,
        "collision_check": plan.get("collision_check", {}),
    }


@navigation_router.post("/navigation/plan/{plan_id}/replan")
async def replan(plan_id: str, req: ReplanRequest) -> Dict[str, Any]:
    if req.plan_id != plan_id:
        raise HTTPException(status_code=400, detail="plan_id mismatch between path and body")
    try:
        if plan_id in _planning.navigators:
            _planning.replan(plan_id, req.new_obstacles)
        elif plan_id in _planning.active_plans:
            base = _planning.active_plans[plan_id]
            path = base.get("path")
            if path is None:
                raise ValueError("Route plan has no path to replan")
            replanned = _planning.plan_route(
                start=path.waypoints[0],
                goal=path.waypoints[-1],
                obstacles=req.new_obstacles,
                planner_type=PlannerType.RRT_STAR,
            )
            _planning.active_plans[plan_id] = replanned
            _planning.active_plans[plan_id]["plan_id"] = plan_id
        else:
            raise ValueError(f"Unknown plan: {plan_id}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("replan", {"plan_id": plan_id, "obstacles": len(req.new_obstacles)})
    return {"status": "replanned", "plan_id": plan_id}


@navigation_router.get("/navigation/plan/{plan_id}/collision-check", response_model=CollisionCheckResponse)
async def get_collision_check(plan_id: str) -> CollisionCheckResponse:
    plan = _planning.active_plans.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    check = plan.get("collision_check")
    if not isinstance(check, dict) or not check:
        path = plan.get("path")
        if path is None:
            raise HTTPException(status_code=404, detail=f"Plan has no path: {plan_id}")
        check = _planning.collision_checker.check_path(path, [])
        plan["collision_check"] = check
    return CollisionCheckResponse(**check)


@navigation_router.post("/navigation/plan/{plan_id}/update")
async def update_navigation(plan_id: str, req: UpdateNavRequest) -> Dict[str, Any]:
    if req.plan_id != plan_id:
        raise HTTPException(status_code=400, detail="plan_id mismatch between path and body")
    if plan_id not in _planning.navigators:
        raise HTTPException(status_code=404, detail=f"Waypoint plan not found: {plan_id}")
    try:
        update = _planning.update_navigation(plan_id, req.to_pose())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return update


@navigation_router.post("/navigation/trajectory/optimize")
async def optimize_trajectory(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_path = payload.get("path")
    platform_type = payload.get("platform_type", "quadrotor")
    if not isinstance(raw_path, dict):
        raise HTTPException(status_code=400, detail="path payload required")
    try:
        path = Path(
            path_id=str(raw_path.get("path_id", "adhoc-path")),
            planner_type=PlannerType.from_value(raw_path.get("planner_type", "straight_line")),
            status=PathStatus(raw_path.get("status", "planned")),
            waypoints=[tuple(wp) for wp in raw_path["waypoints"]],
            total_distance=float(raw_path.get("total_distance", 0.0)),
            estimated_time=float(raw_path.get("estimated_time", 0.0)),
            obstacles_avoided=int(raw_path.get("obstacles_avoided", 0)),
            computation_time_ms=float(raw_path.get("computation_time_ms", 0.0)),
            created_at=_localization.get_state().last_update,
        )
        _ = PlatformType.from_value(platform_type)
        traj = TrajectoryOptimizer().optimize(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"trajectory": _trajectory_response(traj).model_dump()}


@navigation_router.get("/navigation/edge/status")
async def edge_status() -> Dict[str, Any]:
    status = _inference.health_check()
    status["llm"] = _edge_llm.health_check()
    return status


@navigation_router.get("/navigation/edge/models")
async def edge_models() -> Dict[str, Any]:
    optimized = [EdgeModelResponse(**m.to_dict()).model_dump() for m in _optimizer.list_optimized_models()]
    loaded = _inference.list_models()
    return {"optimized_models": optimized, "loaded_models": loaded}


@navigation_router.post("/navigation/edge/models/optimize", response_model=EdgeModelResponse)
async def optimize_model(req: OptimizeModelRequest) -> EdgeModelResponse:
    try:
        model = _optimizer.optimize(req.model_path, precision=req.precision, input_shape=req.input_shape)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("optimize_model", {"model_path": req.model_path, "model_id": model.model_id})
    return EdgeModelResponse(**model.to_dict())


@navigation_router.post("/navigation/edge/predict", response_model=InferenceResultResponse)
async def edge_predict(req: PredictRequest) -> InferenceResultResponse:
    try:
        result = _inference.predict(req.model_id, req.input_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InferenceResultResponse(**result.to_dict())


@navigation_router.get("/navigation/edge/llm/status")
async def edge_llm_status() -> Dict[str, Any]:
    return _edge_llm.health_check()


@navigation_router.get("/navigation/jetson/health", response_model=JetsonStatsResponse)
async def jetson_health() -> JetsonStatsResponse:
    stats = _jetson.get_stats().to_dict()
    stats["simulated"] = _jetson.is_simulated()
    return JetsonStatsResponse(**stats)


@navigation_router.get("/navigation/jetson/memory")
async def jetson_memory() -> Dict[str, Any]:
    return _jetson.get_memory_breakdown()


@navigation_router.get("/navigation/jetson/capabilities")
async def jetson_capabilities() -> Dict[str, Any]:
    info = _jetson.get_cuda_info()
    info["recommended_model_budget_mb"] = _jetson.recommend_model_budget()
    return info
