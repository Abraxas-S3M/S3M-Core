"""FastAPI routes that expose the HOOL engagement pipeline for S3M-Core."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.api.platform_routes import PlatformRegistry, platform_registry
from src.autonomy.engagement_logic import EngagementPipeline, ThreatPrioritizer
from src.platforms.common import ROEProfile, ThreatPriority, Track
from src.platforms.fixed.horizon_adapter import TrackStore


engagement_router = APIRouter()


class TrackInput(BaseModel):
    """Track payload accepted for incremental TrackStore updates."""

    track_id: str = Field(..., min_length=1, max_length=128)
    position: List[float] = Field(..., min_length=3, max_length=3)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification: str = Field(default="unknown", min_length=1, max_length=64)
    threat_priority: str = Field(default=ThreatPriority.MEDIUM.value, min_length=1, max_length=32)
    last_seen: str | None = None

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: List[float]) -> List[float]:
        if len(value) != 3:
            raise ValueError("position must contain exactly three coordinates")
        return [float(value[0]), float(value[1]), float(value[2])]

    def to_track(self) -> Track:
        try:
            priority = ThreatPriority(str(self.threat_priority).lower())
        except Exception as exc:
            raise ValueError(
                "threat_priority must be one of: low, medium, high, critical"
            ) from exc
        if self.last_seen:
            try:
                last_seen = datetime.fromisoformat(self.last_seen)
            except Exception as exc:
                raise ValueError("last_seen must be an ISO-8601 datetime string") from exc
        else:
            last_seen = datetime.now(timezone.utc)
        return Track(
            track_id=self.track_id.strip(),
            position=(self.position[0], self.position[1], self.position[2]),
            confidence=self.confidence,
            classification=self.classification.strip(),
            threat_priority=priority,
            last_seen=last_seen,
        )


class EvaluateRequest(BaseModel):
    """Request body for threat evaluation against current TrackStore state."""

    roe_profile_id: str = Field(default="default", min_length=1, max_length=64)
    ingest_tracks: List[TrackInput] = Field(default_factory=list)
    age_out_stale_tracks: bool = True


class AuthorizeHoolRequest(BaseModel):
    """Request body for HOOL (human-on-the-loop) auto authorization flow."""

    recommendation_id: str = Field(..., min_length=1, max_length=64)
    active_mission_token: bool = True
    allow_auto_engagement: bool = True
    operator_id: str = Field(default="hool-autonomy", min_length=1, max_length=64)


class AuthorizeHotlRequest(BaseModel):
    """Request body for HOTL (human-over-the-loop) engagement authorization."""

    recommendation_id: str = Field(..., min_length=1, max_length=64)
    operator_id: str = Field(..., min_length=1, max_length=64)
    authorize: bool
    rationale: str = Field(default="", max_length=512)


class ROEProfileUpdateRequest(BaseModel):
    """Add or update a named rules-of-engagement profile."""

    profile_id: str = Field(..., min_length=1, max_length=64)
    roe_profile: str = Field(..., min_length=1, max_length=64)
    set_active: bool = True


class BlueForcePosition(BaseModel):
    """Friendly unit position used by threat prioritization heuristics."""

    unit_id: str = Field(..., min_length=1, max_length=64)
    position: List[float] = Field(..., min_length=3, max_length=3)

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: List[float]) -> List[float]:
        if len(value) != 3:
            raise ValueError("position must contain exactly three coordinates")
        return [float(value[0]), float(value[1]), float(value[2])]


class BlueForceUpdateRequest(BaseModel):
    """Bulk blue-force position update payload."""

    positions: List[BlueForcePosition] = Field(default_factory=list)


class _EngagementRuntime:
    """Mutable in-memory state for engagement recommendation and authorization."""

    def __init__(self, registry: PlatformRegistry) -> None:
        self.registry = registry
        self.track_store: TrackStore = self.registry.get_horizon_track_store()
        self.pipeline = EngagementPipeline()
        self.prioritizer = ThreatPrioritizer()
        self.recommendations: Dict[str, Dict[str, Any]] = {}
        self.engagement_log: List[Dict[str, Any]] = []
        self.roe_profiles: Dict[str, ROEProfile] = {"default": ROEProfile.WEAPONS_TIGHT}
        self.active_roe_profile_id = "default"
        self.blue_force_positions: Dict[str, tuple[float, float, float]] = {}

    def log(self, action: str, details: Dict[str, Any]) -> None:
        self.engagement_log.append(
            {
                "id": f"log-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "details": details,
            }
        )
        if len(self.engagement_log) > 5000:
            self.engagement_log = self.engagement_log[-5000:]

    def resolve_roe_profile(self, profile_id: str) -> ROEProfile:
        profile = self.roe_profiles.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"ROE profile not found: {profile_id}")
        return profile

    def store_recommendation(self, recommendation: Dict[str, Any]) -> str:
        recommendation_id = f"rec-{uuid.uuid4().hex[:10]}"
        self.recommendations[recommendation_id] = {
            "payload": recommendation,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return recommendation_id

    def get_recommendation(self, recommendation_id: str) -> Dict[str, Any]:
        recommendation = self.recommendations.get(recommendation_id)
        if recommendation is None:
            raise HTTPException(status_code=404, detail=f"Unknown recommendation_id: {recommendation_id}")
        return recommendation


runtime = _EngagementRuntime(platform_registry)


def _dispatch_effector_action(
    *,
    effector_name: str | None,
    action: str,
    track_id: str,
    mode: str,
    operator_id: str,
    reason: str,
) -> Dict[str, Any]:
    effectors = runtime.registry.get_payload_adapters()
    adapter_result: Dict[str, Any] = {"ok": False, "note": "no effector selected"}
    if not effector_name:
        return adapter_result
    adapter = effectors.get(effector_name)
    if adapter is None:
        return {"ok": False, "note": f"effector not registered: {effector_name}"}

    payload = {
        "action": action,
        "track_id": track_id,
        "mode": mode,
        "operator_id": operator_id,
        "reason": reason,
    }
    if hasattr(adapter, "operator_authorized_action"):
        try:
            result = adapter.operator_authorized_action(payload)
            adapter_result = {"ok": True, "result": result}
        except Exception as exc:  # pragma: no cover - defensive adapter guard
            adapter_result = {"ok": False, "error": str(exc)}
    else:
        # Tactical context: some adapters are monitor-only and cannot execute fire commands.
        adapter_result = {"ok": False, "note": "adapter has no operator_authorized_action hook"}
    return adapter_result


@engagement_router.post("/api/engagement/evaluate")
async def evaluate_engagements(request: EvaluateRequest) -> List[Dict[str, Any]]:
    roe_profile = runtime.resolve_roe_profile(request.roe_profile_id)
    runtime.pipeline.roe_profile = roe_profile

    for track_input in request.ingest_tracks:
        try:
            runtime.track_store.ingest_track(track_input.to_track())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.age_out_stale_tracks:
        runtime.track_store.age_out()

    tracks = runtime.track_store.get_tracks()
    prioritized_tracks = runtime.prioritizer.prioritize_tracks(
        tracks=tracks,
        blue_force_positions=list(runtime.blue_force_positions.values()),
    )
    recommendations = runtime.pipeline.evaluate_threats(
        tracks=prioritized_tracks,
        available_effectors=runtime.registry.get_payload_adapters(),
    )

    response: List[Dict[str, Any]] = []
    for recommendation in recommendations:
        payload = asdict(recommendation)
        recommendation_id = runtime.store_recommendation(payload)
        response.append({"recommendation_id": recommendation_id, **payload})

    runtime.log(
        "evaluate",
        {
            "roe_profile_id": request.roe_profile_id,
            "tracks_in_store": len(tracks),
            "recommendations_returned": len(response),
        },
    )
    return response


@engagement_router.post("/api/engagement/authorize-hool")
async def authorize_hool(request: AuthorizeHoolRequest) -> Dict[str, Any]:
    row = runtime.get_recommendation(request.recommendation_id)
    recommendation = row["payload"]
    authorized = bool(
        request.allow_auto_engagement
        and request.active_mission_token
        and recommendation.get("roe_compliant", False)
        and recommendation.get("recommended_effector")
    )
    action = "engage" if authorized else "hold_fire"
    reason = (
        "HOOL auto-authorization passed mission token and ROE checks"
        if authorized
        else "HOOL auto-authorization blocked by mission token/ROE/effector gates"
    )

    adapter_result = _dispatch_effector_action(
        effector_name=recommendation.get("recommended_effector"),
        action=action,
        track_id=str(recommendation["track_id"]),
        mode="hool",
        operator_id=request.operator_id,
        reason=reason,
    )

    row["status"] = "authorized" if authorized else "held"
    runtime.log(
        "authorize_hool",
        {
            "recommendation_id": request.recommendation_id,
            "authorized": authorized,
            "action": action,
            "operator_id": request.operator_id,
        },
    )
    return {
        "recommendation_id": request.recommendation_id,
        "authorized": authorized,
        "action": action,
        "effector": recommendation.get("recommended_effector"),
        "reason": reason,
        "adapter_result": adapter_result,
    }


@engagement_router.post("/api/engagement/authorize-hotl")
async def authorize_hotl(request: AuthorizeHotlRequest) -> Dict[str, Any]:
    row = runtime.get_recommendation(request.recommendation_id)
    recommendation = row["payload"]
    authorized = bool(
        request.authorize
        and recommendation.get("roe_compliant", False)
        and recommendation.get("recommended_effector")
    )
    action = "engage" if authorized else "hold_fire"
    reason = request.rationale.strip() or (
        "HOTL approved by operator" if authorized else "HOTL denied by operator or ROE"
    )

    adapter_result = _dispatch_effector_action(
        effector_name=recommendation.get("recommended_effector"),
        action=action,
        track_id=str(recommendation["track_id"]),
        mode="hotl",
        operator_id=request.operator_id,
        reason=reason,
    )

    row["status"] = "authorized" if authorized else "held"
    runtime.log(
        "authorize_hotl",
        {
            "recommendation_id": request.recommendation_id,
            "authorized": authorized,
            "action": action,
            "operator_id": request.operator_id,
        },
    )
    return {
        "recommendation_id": request.recommendation_id,
        "authorized": authorized,
        "action": action,
        "effector": recommendation.get("recommended_effector"),
        "reason": reason,
        "adapter_result": adapter_result,
    }


@engagement_router.get("/api/engagement/log")
async def get_engagement_log(limit: int = Query(default=100, ge=1, le=1000)) -> Dict[str, Any]:
    entries = runtime.engagement_log[-limit:]
    return {"entries": entries, "total": len(runtime.engagement_log)}


@engagement_router.post("/api/engagement/roe")
async def upsert_roe_profile(request: ROEProfileUpdateRequest) -> Dict[str, Any]:
    profile_key = str(request.roe_profile).strip().lower()
    try:
        parsed_profile = ROEProfile(profile_key)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="roe_profile must be one of: weapons_hold, weapons_tight, weapons_free",
        ) from exc

    runtime.roe_profiles[request.profile_id] = parsed_profile
    if request.set_active:
        runtime.active_roe_profile_id = request.profile_id
    runtime.log(
        "roe_upsert",
        {
            "profile_id": request.profile_id,
            "roe_profile": parsed_profile.value,
            "set_active": request.set_active,
        },
    )
    return {
        "status": "updated",
        "profile_id": request.profile_id,
        "roe_profile": parsed_profile.value,
        "active_profile_id": runtime.active_roe_profile_id,
    }


@engagement_router.get("/api/engagement/roe")
async def list_roe_profiles() -> Dict[str, Any]:
    profiles = [
        {"profile_id": profile_id, "roe_profile": profile.value}
        for profile_id, profile in runtime.roe_profiles.items()
    ]
    return {"active_profile_id": runtime.active_roe_profile_id, "profiles": profiles}


@engagement_router.post("/api/engagement/blue-force")
async def update_blue_force_positions(request: BlueForceUpdateRequest) -> Dict[str, Any]:
    for position in request.positions:
        runtime.blue_force_positions[position.unit_id] = (
            position.position[0],
            position.position[1],
            position.position[2],
        )
    runtime.log("blue_force_update", {"updated": len(request.positions)})
    return {
        "status": "updated",
        "updated": len(request.positions),
        "total_blue_force_units": len(runtime.blue_force_positions),
    }

