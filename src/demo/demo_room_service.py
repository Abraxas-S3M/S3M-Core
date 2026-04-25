"""FastAPI demo-room service for live tactical client demonstrations."""

from __future__ import annotations

import asyncio
import json
import random
import re
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

TRACK_THEATER_FLAVORS: Dict[str, str] = {
    "saudi_mod": "Arabian Gulf mission theater with Arabic and English operator artifacts.",
    "ukraine_mod": "Eastern Europe defense posture with contested-border intelligence flow.",
    "nato": "Euro-Atlantic coalition operations with multi-domain coordination.",
    "indopac_mod": "Indo-Pacific maritime and littoral defense operating picture.",
    "southam_mod": "South America regional security and sovereignty surveillance operations.",
    "africa_mod": "Africa/Sahel dispersed-terrain stabilization and force protection operations.",
}

VALID_TRACKS = tuple(TRACK_THEATER_FLAVORS.keys())
VALID_PACING = ("realtime", "fast", "instant")
VALID_EVENT_TYPES = (
    "system",
    "engine_status",
    "intel_feed",
    "cop_update",
    "risk_card",
    "artifact",
    "assessment",
    "alert",
)
VALID_ENGINES = ("phi3", "mixtral", "allam", "grok", "null")
SCENARIO_ROOT = Path("/opt/s3m/state/demo/scenarios")

EventType = Literal[
    "system",
    "engine_status",
    "intel_feed",
    "cop_update",
    "risk_card",
    "artifact",
    "assessment",
    "alert",
]
EngineType = Literal["phi3", "mixtral", "allam", "grok", "null"]
PhaseType = Literal["idle", "booting", "running", "complete", "stopped"]


def _model_dump(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


class DemoEvent(BaseModel):
    event_id: str
    timestamp: str
    event_type: EventType
    engine: EngineType
    track: str
    title: str
    body: Dict[str, Any]
    sequence: int = Field(ge=1)
    total: int = Field(ge=1)


class LaunchRequest(BaseModel):
    track: str
    scenario: str = "default"
    pacing: str = "realtime"


class DemoRoom:
    """Maintain one active live demo session for tactical showcase traffic."""

    def __init__(self) -> None:
        self.session_id: Optional[str] = None
        self.track: Optional[str] = None
        self.phase: PhaseType = "idle"
        self.clients: List[WebSocket] = []
        self.events: List[DemoEvent] = []
        self._stream_task: Optional[asyncio.Task[None]] = None
        self._stop_signal = asyncio.Event()
        self._lock = asyncio.Lock()
        self._scenario_name = "default"
        self._pacing = "realtime"

    async def add_client(self, websocket: WebSocket) -> None:
        if websocket not in self.clients:
            self.clients.append(websocket)

    async def remove_client(self, websocket: WebSocket) -> None:
        if websocket in self.clients:
            self.clients.remove(websocket)

    def get_status(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "track": self.track,
            "phase": self.phase,
            "scenario": self._scenario_name,
            "pacing": self._pacing,
            "connected_clients": len(self.clients),
            "event_count": len(self.events),
        }

    async def launch(self, track: str, scenario: str, pacing: str) -> Dict[str, Any]:
        normalized_track = self._validate_track(track)
        normalized_scenario = self._validate_scenario_name(scenario)
        normalized_pacing = self._validate_pacing(pacing)

        async with self._lock:
            await self._cancel_stream_if_running(set_phase=False)
            self.session_id = str(uuid.uuid4())
            self.track = normalized_track
            self.phase = "booting"
            self._scenario_name = normalized_scenario
            self._pacing = normalized_pacing
            self.events = self._load_scenario_events(normalized_track, normalized_scenario)
            self._stop_signal = asyncio.Event()
            self._stream_task = asyncio.create_task(
                self._stream_events_loop(normalized_pacing),
                name=f"demo-room-{self.session_id}",
            )

        await self._broadcast_status()
        return self.get_status()

    async def stop(self) -> Dict[str, Any]:
        async with self._lock:
            await self._cancel_stream_if_running(set_phase=True)
            if self.phase in {"booting", "running"}:
                self.phase = "stopped"
            elif self.phase == "idle":
                self.phase = "stopped"
        await self._broadcast_status()
        return self.get_status()

    async def _cancel_stream_if_running(self, set_phase: bool) -> None:
        self._stop_signal.set()
        task = self._stream_task
        self._stream_task = None
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if set_phase and self.phase != "idle":
            self.phase = "stopped"

    async def _stream_events_loop(self, pacing: str) -> None:
        self.phase = "running"
        await self._broadcast_status()
        try:
            for event in self.events:
                if self._stop_signal.is_set():
                    self.phase = "stopped"
                    await self._broadcast_status()
                    return
                await self._broadcast({"type": "demo_event", "event": _model_dump(event)})
                if event.sequence < event.total:
                    lower, upper = self._event_delay_window(pacing, event)
                    await asyncio.sleep(random.uniform(lower, upper))
            if not self._stop_signal.is_set():
                self.phase = "complete"
                await self._broadcast_status()
        except asyncio.CancelledError:
            self.phase = "stopped"
            await self._broadcast_status()
            raise
        finally:
            self._stream_task = None

    async def _broadcast_status(self) -> None:
        await self._broadcast({"type": "status", "status": self.get_status()})

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        stale_clients: List[WebSocket] = []
        for client in list(self.clients):
            try:
                await client.send_json(payload)
            except Exception:
                stale_clients.append(client)
        for stale in stale_clients:
            await self.remove_client(stale)

    def _event_delay_window(self, pacing: str, event: DemoEvent) -> tuple[float, float]:
        base_windows = {
            "realtime": (3.0, 8.0),
            "fast": (1.0, 3.0),
            "instant": (0.3, 0.5),
        }
        low, high = base_windows[pacing]
        multiplier = 1.0
        if event.event_type == "engine_status":
            multiplier = 0.6  # Engine boot chatter is compressed for concise tactical demos.
        elif event.event_type == "assessment":
            multiplier = 1.4  # Assessment cards stay longer for operator discussion.
        return low * multiplier, high * multiplier

    def _load_scenario_events(self, track: str, scenario: str) -> List[DemoEvent]:
        scenario_path = SCENARIO_ROOT / track / f"{scenario}.jsonl"
        if not scenario_path.exists():
            return self._fallback_scenario(track)

        parsed_events: List[DemoEvent] = []
        with scenario_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                with suppress(json.JSONDecodeError):
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        parsed_events.append(self._coerce_event(payload, track))

        if not parsed_events:
            return self._fallback_scenario(track)

        return self._numbered_events(parsed_events)

    def _coerce_event(self, payload: Dict[str, Any], track: str) -> DemoEvent:
        event_type = str(payload.get("event_type", "intel_feed")).lower()
        if event_type not in VALID_EVENT_TYPES:
            event_type = "intel_feed"
        engine = payload.get("engine", "null")
        engine_value = str(engine).lower() if engine is not None else "null"
        if engine_value not in VALID_ENGINES:
            engine_value = "null"
        timestamp = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())
        title = str(payload.get("title") or f"{event_type.replace('_', ' ').title()} event")
        body = payload.get("body", {})
        if not isinstance(body, dict):
            body = {"note": "Invalid body payload replaced with tactical placeholder."}

        return DemoEvent(
            event_id=str(payload.get("event_id") or str(uuid.uuid4())),
            timestamp=timestamp,
            event_type=event_type,  # type: ignore[arg-type]
            engine=engine_value,  # type: ignore[arg-type]
            track=track,
            title=title,
            body=body,
            sequence=1,
            total=1,
        )

    def _fallback_scenario(self, track: str) -> List[DemoEvent]:
        theater = TRACK_THEATER_FLAVORS[track]
        bilingual_body = {
            "english": "Coalition checkpoint confirms secure corridor and friendly force posture.",
            "arabic": "تأكيد نقطة التفتيش للتحالف يؤكد سلامة الممر واستقرار وضع القوات الصديقة.",
            "classification": "UNCLASSIFIED",
        }
        events_payload = [
            {
                "event_type": "system",
                "engine": "null",
                "title": "System initialization",
                "body": {
                    "summary": "Demo room initialized for tactical showcase.",
                    "theater": theater,
                },
            },
            {
                "event_type": "engine_status",
                "engine": "phi3",
                "title": "Engine boot",
                "body": {"status": "phi3 online", "role": "rapid field reasoning"},
            },
            {
                "event_type": "engine_status",
                "engine": "mixtral",
                "title": "Engine boot",
                "body": {"status": "mixtral online", "role": "multi-perspective synthesis"},
            },
            {
                "event_type": "engine_status",
                "engine": "allam",
                "title": "Engine boot",
                "body": {"status": "allam online", "role": "Arabic-language analyst support"},
            },
            {
                "event_type": "engine_status",
                "engine": "grok",
                "title": "Engine boot",
                "body": {"status": "grok online", "role": "oracle-style strategic checks"},
            },
            {
                "event_type": "intel_feed",
                "engine": "null",
                "title": "Intel feed update",
                "body": {
                    "priority": "high",
                    "summary": "ISR sweep detected abnormal logistics convoys near objective route.",
                },
            },
            {
                "event_type": "cop_update",
                "engine": "null",
                "title": "COP refresh",
                "body": {
                    "overlay": "joint-force-ops",
                    "summary": "Common operational picture synchronized with allied unit telemetry.",
                },
            },
            {
                "event_type": "risk_card",
                "engine": "mixtral",
                "title": "Risk card generated",
                "body": {
                    "risk": "Counter-battery exposure",
                    "severity": "medium",
                    "mitigation": "Stagger maneuver windows and maintain decoy signatures.",
                },
            },
            {
                "event_type": "artifact",
                "engine": "allam",
                "title": "Bilingual artifact produced",
                "body": bilingual_body if track == "saudi_mod" else {"english": theater},
            },
            {
                "event_type": "assessment",
                "engine": "grok",
                "title": "Grok Oracle assessment",
                "body": {
                    "criteria_scores": {
                        "mission_readiness": 0.92,
                        "force_protection": 0.87,
                        "intelligence_quality": 0.89,
                        "decision_confidence": 0.9,
                    },
                    "recommendation": "Proceed with controlled tempo and contingency reserve.",
                },
            },
            {
                "event_type": "alert",
                "engine": "null",
                "title": "Pipeline complete",
                "body": {
                    "status": "complete",
                    "message": "Demo storyline reached tactical completion checkpoint.",
                },
            },
        ]

        seed_events = [
            DemoEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=payload["event_type"],  # type: ignore[arg-type]
                engine=payload["engine"],  # type: ignore[arg-type]
                track=track,
                title=payload["title"],
                body=payload["body"],
                sequence=1,
                total=1,
            )
            for payload in events_payload
        ]
        return self._numbered_events(seed_events)

    def _numbered_events(self, events: List[DemoEvent]) -> List[DemoEvent]:
        total = len(events)
        numbered_events: List[DemoEvent] = []
        for index, event in enumerate(events, start=1):
            payload = _model_dump(event)
            payload["sequence"] = index
            payload["total"] = total
            numbered_events.append(DemoEvent(**payload))
        return numbered_events

    def _validate_track(self, track: str) -> str:
        normalized_track = str(track).strip()
        if normalized_track not in VALID_TRACKS:
            raise ValueError(f"Invalid track: {normalized_track}")
        return normalized_track

    def _validate_scenario_name(self, scenario: str) -> str:
        normalized_scenario = str(scenario).strip() or "default"
        if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized_scenario):
            raise ValueError("Scenario name must be alphanumeric with optional '-' or '_'")
        return normalized_scenario

    def _validate_pacing(self, pacing: str) -> str:
        normalized_pacing = str(pacing).strip().lower()
        if normalized_pacing not in VALID_PACING:
            raise ValueError(f"Invalid pacing: {normalized_pacing}")
        return normalized_pacing


demo_room = DemoRoom()
router = APIRouter(prefix="/api/demo", tags=["Demo Room"])


@router.post("/launch")
async def launch_demo(request: LaunchRequest) -> Dict[str, Any]:
    try:
        status = await demo_room.launch(
            track=request.track,
            scenario=request.scenario,
            pacing=request.pacing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Demo launched", "status": status}


@router.post("/stop")
async def stop_demo() -> Dict[str, Any]:
    status = await demo_room.stop()
    return {"message": "Demo stopped", "status": status}


@router.get("/status")
async def demo_status() -> Dict[str, Any]:
    return demo_room.get_status()


@router.get("/tracks")
async def demo_tracks() -> Dict[str, Any]:
    return {
        "tracks": [
            {"name": track_name, "theater": flavor}
            for track_name, flavor in TRACK_THEATER_FLAVORS.items()
        ]
    }


async def demo_ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await demo_room.add_client(websocket)
    await websocket.send_json({"type": "status", "status": demo_room.get_status()})
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "detail": "Command must be a JSON object"})
                continue
            command = str(message.get("command", "")).strip().lower()
            if command == "launch":
                payload = message.get("payload", message)
                if not isinstance(payload, dict):
                    await websocket.send_json({"type": "error", "detail": "Launch payload must be a JSON object"})
                    continue
                try:
                    request = LaunchRequest(**payload)
                    status = await demo_room.launch(
                        track=request.track,
                        scenario=request.scenario,
                        pacing=request.pacing,
                    )
                    await websocket.send_json({"type": "status", "status": status})
                except ValueError as exc:
                    await websocket.send_json({"type": "error", "detail": str(exc)})
            elif command == "stop":
                status = await demo_room.stop()
                await websocket.send_json({"type": "status", "status": status})
            elif command == "status":
                await websocket.send_json({"type": "status", "status": demo_room.get_status()})
            else:
                await websocket.send_json(
                    {"type": "error", "detail": "Unsupported command. Use launch, stop, or status."}
                )
    except WebSocketDisconnect:
        pass
    finally:
        await demo_room.remove_client(websocket)
