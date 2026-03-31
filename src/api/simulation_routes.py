"""FastAPI routes for S3M Layer 04 Simulation & Wargaming."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.api.simulation_models import (
    AARReportResponse,
    ConnectSimulatorRequest,
    GenerateOpForRequest,
    LoadScenarioRequest,
    ReplayArtifactResponse,
    RunScenarioRequest,
    ScenarioStatusResponse,
    SimEntityResponse,
    SimulationStateResponse,
    SimulationStatusResponse,
    SyntheticDatasetResponse,
)
from src.simulation.adapters import AirSimAdapter, BuiltinPhysicsEngine, GazeboAdapter, JSBSimAdapter, PanopticonAdapter
from src.simulation.models import SimConfig, SimulationState
from src.simulation.synthetic import SyntheticDataManager
from src.simulation.wargame import ForceBuilder, OpForGenerator, ScenarioEngine, ScenarioRunner

simulation_router = APIRouter()

_scenario_engine = ScenarioEngine()
_synthetic = SyntheticDataManager()
_force_builder = ForceBuilder()

_adapters: Dict[str, Any] = {
    "builtin": BuiltinPhysicsEngine(SimConfig(simulator_name="builtin", host="localhost", port=0)),
    "gazebo": GazeboAdapter(SimConfig(simulator_name="gazebo", host="localhost", port=11345)),
    "airsim": AirSimAdapter(SimConfig(simulator_name="airsim", host="localhost", port=41451)),
    "jsbsim": JSBSimAdapter(SimConfig(simulator_name="jsbsim", host="localhost", port=0)),
    "panopticon": PanopticonAdapter(SimConfig(simulator_name="panopticon", host="localhost", port=5000)),
}
_runner = ScenarioRunner(adapter=_adapters["builtin"])
_loaded_scenario = None
_audit: list[dict] = []


def _audit_log(action: str, details: Dict[str, Any]) -> None:
    _audit.append(
        {
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    if len(_audit) > 1000:
        del _audit[:-1000]


def _state_response(state: SimulationState) -> SimulationStateResponse:
    entities = [
        SimEntityResponse(
            entity_id=e.entity_id,
            entity_type=e.entity_type.value,
            position=e.position,
            velocity=e.velocity,
            heading=e.heading,
            health=e.health,
            active=e.active,
            metadata=e.metadata,
        )
        for e in state.entities
    ]
    return SimulationStateResponse(
        timestamp=state.timestamp.isoformat(),
        sim_time_seconds=state.sim_time_seconds,
        entities=entities,
        terrain=state.terrain,
        weather=state.weather,
        active_events=state.active_events,
        metadata=state.metadata,
    )


@simulation_router.get("/simulation/status", response_model=SimulationStatusResponse)
async def simulation_status() -> SimulationStatusResponse:
    """Return overall health for Layer 04 simulation subsystem."""
    status = {
        name: adapter.health_check()
        for name, adapter in _adapters.items()
    }
    active_adapter = _runner.adapter.config.simulator_name if _runner and _runner.adapter else "unknown"
    replay_count = len(_runner.replay_recorder.list_replays())
    dataset_count = len(_synthetic.list_datasets())
    return SimulationStatusResponse(
        status="operational",
        adapters=status,
        active_adapter=active_adapter,
        loaded_scenarios=1 if _loaded_scenario else 0,
        dataset_count=dataset_count,
        replay_count=replay_count,
    )


@simulation_router.get("/simulation/adapters")
async def list_adapters() -> Dict[str, Any]:
    """List adapters with current availability and health."""
    return {
        "adapters": [
            {"name": name, **adapter.health_check()}
            for name, adapter in _adapters.items()
        ]
    }


@simulation_router.post("/simulation/adapters/{name}/connect")
async def connect_adapter(name: str, req: ConnectSimulatorRequest) -> Dict[str, Any]:
    """Connect named simulator adapter with provided host/port config."""
    adapter = _adapters.get(name)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"adapter not found: {name}")
    adapter.config.host = req.host
    adapter.config.port = req.port
    adapter.config.world_file = req.world_file
    adapter.config.headless = req.headless
    adapter.config.extra_params.update(req.extra_params)
    ok = adapter.connect()
    _audit_log("adapter_connect", {"adapter": name, "connected": ok})
    if not ok:
        raise HTTPException(status_code=400, detail=f"failed to connect adapter: {name}")
    return {"status": "connected", "adapter": name, "connected": True}


@simulation_router.post("/simulation/adapters/{name}/disconnect")
async def disconnect_adapter(name: str) -> Dict[str, Any]:
    """Disconnect named simulation adapter."""
    adapter = _adapters.get(name)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"adapter not found: {name}")
    adapter.disconnect()
    _audit_log("adapter_disconnect", {"adapter": name})
    return {"status": "disconnected", "adapter": name}


@simulation_router.get("/simulation/adapters/{name}/state", response_model=SimulationStateResponse)
async def get_adapter_state(name: str) -> SimulationStateResponse:
    """Fetch current simulation state from selected adapter."""
    adapter = _adapters.get(name)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"adapter not found: {name}")
    state = adapter.get_state()
    return _state_response(state)


@simulation_router.get("/simulation/scenarios")
async def list_scenarios() -> Dict[str, Any]:
    """List scenario YAMLs available under configs/scenarios."""
    scenarios = _scenario_engine.list_scenarios()
    return {"scenarios": scenarios, "total": len(scenarios)}


@simulation_router.post("/simulation/scenarios/load")
async def load_scenario(req: LoadScenarioRequest) -> Dict[str, Any]:
    """Load scenario from YAML file path or inline payload into runner."""
    global _loaded_scenario
    try:
        if req.yaml_path:
            scenario = _scenario_engine.load_from_yaml(req.yaml_path)
        elif req.inline:
            scenario = _scenario_engine.load_from_dict(req.inline)
        else:
            raise ValueError("either yaml_path or inline must be provided")
        _runner.load(scenario)
        _loaded_scenario = scenario
        _audit_log("scenario_load", {"scenario_id": scenario.scenario_id, "name": scenario.name})
        return {"status": "loaded", "scenario_id": scenario.scenario_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@simulation_router.post("/simulation/scenarios/{scenario_id}/run", response_model=AARReportResponse)
async def run_scenario(scenario_id: str, req: RunScenarioRequest) -> AARReportResponse:
    """Execute loaded scenario and return generated AAR."""
    if _loaded_scenario is None or _loaded_scenario.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail=f"scenario not loaded: {scenario_id}")
    opfor = OpForGenerator(strategy=req.opfor_strategy)
    try:
        aar = _runner.run(max_ticks=req.max_ticks, tick_dt=req.tick_dt, opfor_controller=opfor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_log("scenario_run", {"scenario_id": scenario_id, "outcome": aar.outcome})
    return AARReportResponse(**aar.to_dict())


@simulation_router.post("/simulation/scenarios/{scenario_id}/stop")
async def stop_scenario(scenario_id: str) -> Dict[str, Any]:
    """Stop currently running scenario."""
    _runner.stop()
    _audit_log("scenario_stop", {"scenario_id": scenario_id})
    return {"status": "stopped", "scenario_id": scenario_id}


@simulation_router.get("/simulation/scenarios/{scenario_id}/status", response_model=ScenarioStatusResponse)
async def scenario_status(scenario_id: str) -> ScenarioStatusResponse:
    """Return execution status for scenario runner."""
    status = _runner.get_status()
    return ScenarioStatusResponse(**status)


@simulation_router.get("/simulation/scenarios/{scenario_id}/aar", response_model=AARReportResponse)
async def get_aar(scenario_id: str) -> AARReportResponse:
    """Return AAR generated from last scenario run."""
    aar = _runner.get_aar()
    if aar is None or aar.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail=f"AAR not found for scenario: {scenario_id}")
    return AARReportResponse(**aar.to_dict())


@simulation_router.post("/simulation/wargame/opfor/generate")
async def generate_opfor(req: GenerateOpForRequest) -> Dict[str, Any]:
    """Generate OPFOR behaviors using requested strategy and difficulty."""
    state = _runner.adapter.get_state()
    generator = OpForGenerator(strategy=req.strategy)
    generator.set_difficulty(req.difficulty)
    behaviors = generator.generate_behavior(state)
    return {"behaviors": behaviors, "count": len(behaviors)}


@simulation_router.post("/simulation/wargame/forces/build")
async def build_force(body: Dict[str, Any]) -> Dict[str, Any]:
    """Build force composition from template or custom units."""
    template = str(body.get("template", "")).strip().lower()
    if template == "patrol":
        force = _force_builder.create_standard_patrol_force()
    elif template == "opfor":
        force = _force_builder.create_standard_opfor()
    elif template == "air_defense":
        force = _force_builder.create_air_defense_force()
    elif template == "convoy":
        force = _force_builder.create_convoy()
    else:
        try:
            force = _force_builder.create_force(
                name=str(body.get("name", "Custom Force")),
                allegiance=str(body.get("allegiance", "friendly")),
                units=list(body.get("units", [])),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"force": force.to_dict()}


@simulation_router.post("/simulation/synthetic/generate", response_model=SyntheticDatasetResponse)
async def generate_synthetic(body: Dict[str, Any]) -> SyntheticDatasetResponse:
    """Generate synthetic dataset by requested type and parameters."""
    dtype = str(body.get("type", body.get("data_type", ""))).strip().lower()
    params = dict(body.get("params", {}))
    try:
        if dtype == "network":
            dataset = _synthetic.generate_network_traffic(
                n_records=int(body.get("n_records", 10000)),
                attack_ratio=float(params.get("attack_ratio", 0.1)),
            )
        elif dtype == "sensor":
            dataset = _synthetic.generate_sensor_telemetry(
                n_records=int(body.get("n_records", 5000)),
                n_sensors=int(params.get("n_sensors", 10)),
                anomaly_ratio=float(params.get("anomaly_ratio", 0.05)),
            )
        elif dtype == "logistics":
            dataset = _synthetic.generate_logistics_data(
                n_records=int(body.get("n_records", 2000)),
            )
        elif dtype == "trajectory":
            dataset = _synthetic.generate_uav_trajectories(
                n_agents=int(params.get("n_agents", body.get("n_agents", 4))),
                duration=float(params.get("duration", body.get("duration", 120.0))),
            )
        elif dtype == "scenario":
            dataset = _synthetic.generate_threat_scenarios(
                n_scenarios=int(params.get("n_scenarios", 10)),
                events_per=int(params.get("events_per", 100)),
            )
        else:
            raise ValueError("type must be one of network/sensor/logistics/trajectory/scenario")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_log("synthetic_generate", {"dataset_id": dataset.dataset_id, "type": dtype})
    return SyntheticDatasetResponse(**dataset.to_dict())


@simulation_router.get("/simulation/synthetic/datasets")
async def list_synthetic_datasets() -> Dict[str, Any]:
    """List synthetic datasets from manifest."""
    datasets = _synthetic.list_datasets()
    return {"datasets": [dataset.to_dict() for dataset in datasets], "total": len(datasets)}


@simulation_router.get("/simulation/synthetic/datasets/{dataset_id}", response_model=SyntheticDatasetResponse)
async def synthetic_dataset_detail(dataset_id: str) -> SyntheticDatasetResponse:
    """Return one synthetic dataset metadata entry."""
    dataset = _synthetic.manifest.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"dataset not found: {dataset_id}")
    return SyntheticDatasetResponse(**dataset.to_dict())


@simulation_router.post("/simulation/synthetic/datasets/{dataset_id}/verify")
async def verify_synthetic_dataset(dataset_id: str) -> Dict[str, Any]:
    """Verify checksum for selected synthetic dataset."""
    ok = _synthetic.verify_dataset(dataset_id)
    return {"dataset_id": dataset_id, "valid": ok}


@simulation_router.get("/simulation/replays")
async def list_replays() -> Dict[str, Any]:
    """List replay artifacts recorded by scenario runner."""
    artifacts = _runner.replay_recorder.list_replays()
    return {"replays": [artifact.to_dict() for artifact in artifacts], "total": len(artifacts)}


@simulation_router.get("/simulation/replays/{replay_id}", response_model=ReplayArtifactResponse)
async def replay_detail(replay_id: str) -> ReplayArtifactResponse:
    """Get replay artifact metadata by replay ID."""
    artifacts = _runner.replay_recorder.list_replays()
    for artifact in artifacts:
        if artifact.replay_id == replay_id:
            return ReplayArtifactResponse(**artifact.to_dict())
    raise HTTPException(status_code=404, detail=f"replay not found: {replay_id}")
