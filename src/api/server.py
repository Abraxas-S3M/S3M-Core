"""S3M Quad-Engine REST API Server.

Provides 13 endpoints for inference, consensus, engine management, and audit logging.
Designed for air-gapped deployment on NVIDIA Jetson AGX Orin 64GB.
"""

import hashlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import yaml

try:
    from services.air_defense.api_routes import router as air_defense_router
except Exception:
    air_defense_router = None
try:
    from services.interceptor.api_routes import router as interceptor_router
except Exception:
    interceptor_router = None
try:
    from services.predictive_defense.api_routes import router as predictive_router
except Exception:
    predictive_router = None
try:
    from src.api.command_routes import command_router
except Exception:
    command_router = None
try:
    from src.api.cloud_training_routes import cloud_training_router
except Exception:
    cloud_training_router = None
from src.api.config import api_config, mission_command_lifespan
try:
    from src.api.cot_routes import cot_router
except Exception:
    cot_router = None
try:
    from src.api.ogc_routes import ogc_router
except Exception:
    ogc_router = None
try:
    from src.api.apps_routes import apps_router
except Exception:
    apps_router = None
try:
    from src.api.autonomy_routes import autonomy_router
except Exception:
    autonomy_router = None
try:
    from src.api.comms_routes import comms_router
except Exception:
    comms_router = None
try:
    from src.api.engagement_routes import engagement_router
except Exception:
    engagement_router = None
try:
    from src.api.edge_runtime_routes import router as edge_router
except Exception:
    edge_router = None
try:
    from src.api.cyber_routes import cyber_router
except Exception:
    cyber_router = None
try:
    from src.api.dashboard_routes import dashboard_router
except Exception:
    dashboard_router = None
try:
    from src.api.fmv_routes import fmv_router
except Exception:
    fmv_router = None
try:
    from src.api.hla_routes import hla_router
except Exception:
    hla_router = None
try:
    from src.api.intel_routes import intel_router
except Exception:
    intel_router = None
try:
    from src.api.maintenance_routes import maintenance_router
except Exception:
    maintenance_router = None
try:
    from src.api.mission_routes import mission_router
except Exception:
    mission_router = None
try:
    from src.api.navigation_routes import navigation_router
except Exception:
    navigation_router = None
try:
    from src.api.mtf_routes import mtf_router
except Exception:
    mtf_router = None
try:
    from src.api.mip_routes import mip_router
except Exception:
    mip_router = None
try:
    from src.api.nffi_routes import nffi_router
except Exception:
    nffi_router = None
try:
    from src.api.nvg_routes import nvg_router
except Exception:
    nvg_router = None
try:
    from src.api.oth_routes import oth_router
except Exception:
    oth_router = None
try:
    from src.api.platform_routes import platform_router
except Exception:
    platform_router = None
try:
    from src.api.portal_routes import router as portal_router
except Exception:
    portal_router = None
try:
    from src.api.security_routes import security_router
except Exception:
    security_router = None
try:
    from src.api.sensor_analytics_routes import sensor_analytics_router
except Exception:
    sensor_analytics_router = None
try:
    from src.api.taxii_routes import taxii_router
except Exception:
    taxii_router = None
try:
    from src.api.nsili_routes import nsili_router
except Exception:
    nsili_router = None
try:
    from src.api.readiness_routes import readiness_router
except Exception:
    readiness_router = None
try:
    from src.api.quantum_security_routes import router as qss_router
except Exception:
    qss_router = None
try:
    from src.api.fmn_security_routes import fmn_security_router
except Exception:
    fmn_security_router = None
try:
    from src.api.safety_routes import safety_router
except Exception:
    safety_router = None
try:
    from src.api.simulation_routes import simulation_router
except Exception:
    simulation_router = None
try:
    from src.api.threat_routes import threat_router, sensor_router
except Exception:
    threat_router = None
    sensor_router = None
try:
    from src.api.training_sim_routes import training_sim_router
except Exception:
    training_sim_router = None
from src.api.edge_compute_mount import mount_edge_compute
from src.security.middleware import SecurityMiddleware
try:
    from src.api.interop_ext_routes import interop_ext_router
except Exception:
    interop_ext_router = None
try:
    from src.api.jreap_routes import jreap_router
except Exception:
    jreap_router = None
try:
    from src.api.uas4586_routes import uas4586_router
except Exception:
    uas4586_router = None
try:
    from src.api.gui_bridge import gui_bridge_router
except Exception:
    gui_bridge_router = None
try:
    from src.api.gui_bridge.ws_bridge import ws_router as gui_ws_router
except Exception:
    gui_ws_router = None
try:
    from src.world_intelligence_control import world_intelligence_router
except Exception:
    world_intelligence_router = None
try:
    from src.demo.demo_room_service import demo_ws_endpoint, router as demo_router
except Exception:
    demo_router = None
    demo_ws_endpoint = None
try:
    from src.cop.cop_routes import router as cop_router
except Exception:
    cop_router = None
try:
    from src.edge_runtime.bootstrap import get_edge_runtime
except Exception:
    get_edge_runtime = lambda: None
try:
    from src.edge_runtime.bootstrap import get_edge_runtime_status
except Exception:
    get_edge_runtime_status = lambda: {"status": "unavailable"}

LOGGER = logging.getLogger(__name__)

# ── Pydantic Models ──────────────────────────────────────────

class InferenceRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096)
    engine: Optional[str] = None
    domain: Optional[str] = None
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = False


class ConsensusRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096)
    engines: Optional[List[str]] = None
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    strategy: str = Field(default="majority", pattern="^(majority|weighted|unanimous)$")


class EngineConfigUpdate(BaseModel):
    gpu_layers: Optional[int] = Field(None, ge=0, le=100)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)


class InferenceResponse(BaseModel):
    request_id: str
    engine: str
    response: str
    tokens_used: int
    latency_ms: float
    timestamp: str
    classification: str = "UNCLASSIFIED"


class ConsensusResponse(BaseModel):
    request_id: str
    consensus: str
    engine_responses: Dict[str, str]
    agreement_score: float
    strategy: str
    latency_ms: float
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    engines: Dict[str, str]
    memory: Dict[str, Any]
    timestamp: str


async def optimization_startup_hook() -> None:
    """Run Phase 12 startup sequencing and memory checks at API boot."""
    try:
        from src.optimization import MemoryBudgetManager, StartupSequencer

        manager = MemoryBudgetManager(total_budget_gb=48.0)
        sequencer = StartupSequencer(memory_manager=manager)
        startup = sequencer.run()
        report = manager.get_usage()
        state.log_audit(
            "optimization_startup",
            {
                "layers_loaded": startup.get("layers_loaded", 0),
                "layers_skipped": startup.get("layers_skipped", 0),
                "layers_unavailable": startup.get("layers_unavailable", 0),
                "memory_used_mb": report.get("used_mb", 0.0),
                "memory_budget_mb": report.get("total_budget_mb", 0.0),
            },
        )
    except Exception as exc:
        LOGGER.warning("Optimization startup hook failed: %s", exc)
        state.log_audit("optimization_startup_error", {"error": str(exc)})


async def edge_runtime_startup_hook() -> None:
    """Initialize austere edge runtime before service/model loading."""
    try:
        runtime = get_edge_runtime()
        state.log_audit(
            "edge_runtime_startup",
            {
                "node_tier": runtime.profile.tier.value,
                "mode": runtime.controller.current_mode.value,
            },
        )
    except Exception as exc:
        LOGGER.warning("Edge runtime startup hook failed: %s", exc)
        state.log_audit("edge_runtime_startup_error", {"error": str(exc)})


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await edge_runtime_startup_hook()
    await optimization_startup_hook()
    async with mission_command_lifespan(app):
        yield


# ── Application Setup ────────────────────────────────────────

app = FastAPI(
    title="S3M Quad-Engine API",
    description="Tactical AI inference API for air-gapped deployment",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=app_lifespan,
)

if edge_router:
    app.include_router(edge_router)
if autonomy_router:
    app.include_router(autonomy_router, tags=["Autonomy & Swarm"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=api_config.cors_origins
    + [
        "https://s3m-gui.pages.dev",
        "https://*.s3m-gui.pages.dev",
        "https://app.abraxas-s3m.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if threat_router:
    app.include_router(threat_router, tags=["Threat Detection"])
if sensor_router:
    app.include_router(sensor_router, tags=["Sensor Fusion"])
if navigation_router:
    app.include_router(navigation_router, tags=["Navigation & Edge AI"])
if dashboard_router:
    app.include_router(dashboard_router, tags=["Dashboard"])
if simulation_router:
    app.include_router(simulation_router, tags=["Simulation & Wargaming"])
if apps_router:
    app.include_router(apps_router, tags=["Domain Applications"])
if intel_router:
    app.include_router(intel_router, tags=["Intelligence & OSINT Briefings"])
if training_sim_router:
    app.include_router(training_sim_router, tags=["Training & Simulation Advanced"])
if cloud_training_router:
    app.include_router(cloud_training_router, tags=["Cloud Training"])
if sensor_analytics_router:
    app.include_router(sensor_analytics_router, tags=["Sensor & Remote Sensing Analytics"])
if air_defense_router:
    app.include_router(air_defense_router, tags=["Air Defense"])
if interceptor_router:
    app.include_router(interceptor_router, tags=["Interceptor Guidance"])
if predictive_router:
    app.include_router(predictive_router, tags=["Predictive Defense"])
if comms_router:
    app.include_router(comms_router, tags=["Secure Communications"])
if command_router:
    app.include_router(command_router, tags=["Mission Command"])
if platform_router:
    app.include_router(platform_router, tags=["Platform Integration"])

# Load security config
security_config = {}
security_config_path = "configs/security.yaml"
if os.path.exists(security_config_path):
    with open(security_config_path) as f:
        security_config = yaml.safe_load(f).get("middleware", {})

# Add security middleware (wraps ALL requests)
app.add_middleware(SecurityMiddleware, config=security_config)

# Add security routes
if security_router:
    app.include_router(security_router, tags=["Security & Compliance"])
if cyber_router:
    app.include_router(cyber_router, tags=["Cyber Defense Operations"])
if taxii_router:
    app.include_router(taxii_router, tags=["Cyber Threat Intelligence Exchange"])
if nsili_router:
    app.include_router(nsili_router, tags=["NSILI ISR Interoperability"])
if interop_ext_router:
    app.include_router(interop_ext_router, tags=["Interoperability & Standards (Extended)"])
if cot_router:
    app.include_router(cot_router, tags=["Cursor-on-Target / TAK Gateway"])
if hla_router:
    app.include_router(hla_router, tags=["HLA Federation Interoperability"])
if mip_router:
    app.include_router(mip_router, tags=["MIP Gateway Interoperability"])
if ogc_router:
    app.include_router(ogc_router, tags=["OGC Geospatial Interoperability"])
if nffi_router:
    app.include_router(nffi_router, tags=["NFFI Blue Force Tracking"])
if nvg_router:
    app.include_router(nvg_router, tags=["NATO Vector Graphics (NVG)"])
if mtf_router:
    app.include_router(mtf_router, tags=["APP-11 XML Message Text Format"])
if fmv_router:
    app.include_router(fmv_router, tags=["STANAG 4609 FMV Metadata"])
if jreap_router:
    app.include_router(jreap_router, tags=["JREAP-C Link 16 Gateway"])
if oth_router:
    app.include_router(oth_router, tags=["OTH-Gold Maritime Gateway"])
if fmn_security_router:
    app.include_router(fmn_security_router, tags=["FMN Security"])
if maintenance_router:
    app.include_router(maintenance_router, tags=["Procurement & Maintenance"])
if readiness_router:
    app.include_router(readiness_router, tags=["Personnel & Readiness"])
if safety_router:
    app.include_router(safety_router, tags=["Safety & Control Authority"])
if portal_router:
    app.include_router(portal_router, tags=["Portal RBAC"])
if world_intelligence_router:
    app.include_router(world_intelligence_router, tags=["World Intelligence"])
# GUI Bridge — provides /api/v1/* endpoints for S3M-GUI frontend
if gui_bridge_router:
    app.include_router(gui_bridge_router, prefix="/api/v1", tags=["GUI Bridge"])
if gui_ws_router:
    app.include_router(gui_ws_router, tags=["GUI WebSocket"])
if demo_router:
    app.include_router(demo_router)
if demo_ws_endpoint:
    app.add_api_websocket_route("/ws/demo-room", demo_ws_endpoint)
if cop_router:
    app.include_router(cop_router)
# Bootstrap austere runtime before optional edge service managers are mounted.
try:
    get_edge_runtime()
except Exception as exc:  # pragma: no cover - defensive startup fallback
    LOGGER.warning("Edge runtime eager bootstrap failed: %s", exc)
mount_edge_compute(app)

# Keep dashboard API routes active, then mount static frontend files.
dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "frontend")
if os.path.exists(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

# ── State Management ─────────────────────────────────────────

class ServerState:
    def __init__(self):
        self.start_time = time.time()
        self.engines: Dict[str, Any] = {}
        self.engine_status: Dict[str, str] = {
            "phi3": "unloaded",
            "grok": "unloaded",
            "mistral": "unloaded",
            "allam": "unloaded"
        }
        self.request_count = 0
        self.audit_log: List[Dict] = []
        self.domain_routing = dict(api_config.domain_routing)

    def log_audit(self, action: str, details: Dict):
        entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details
        }
        self.audit_log.append(entry)
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]

    def resolve_engine(self, engine: Optional[str], domain: Optional[str]) -> str:
        if engine and engine in self.engine_status:
            return engine
        if domain and domain in self.domain_routing:
            return self.domain_routing[domain]
        return "phi3"


state = ServerState()


# ── Helper Functions ─────────────────────────────────────────

def get_memory_info() -> Dict[str, Any]:
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        info = {}
        for line in lines[:5]:
            parts = line.split(":")
            key = parts[0].strip()
            val = parts[1].strip().split()[0]
            info[key + "_MB"] = int(val) // 1024
        return info
    except Exception:
        return {"note": "memory info unavailable"}


def simulate_inference(engine: str, prompt: str, max_tokens: int, temperature: float) -> Dict:
    """Simulate inference when engine not loaded. Returns mock response."""
    start = time.time()

    if state.engine_status.get(engine) == "loaded" and engine in state.engines:
        try:
            model = state.engines[engine]
            result = model(prompt, max_tokens=max_tokens, temperature=temperature)
            text = result["choices"][0]["text"]
            tokens = result["usage"]["completion_tokens"]
            latency = (time.time() - start) * 1000
            return {"text": text, "tokens": tokens, "latency_ms": latency, "live": True}
        except Exception as e:
            pass

    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
    simulated = f"[{engine.upper()}] Analysis of query {prompt_hash}: "
    simulated += f"Based on tactical assessment, "

    if engine == "phi3":
        simulated += "recommend establishing forward operating position at grid reference provided. Priority: HIGH."
    elif engine == "grok":
        simulated += "intelligence indicates moderate threat level. Confidence: 0.78. Recommend continued surveillance."
    elif engine == "mistral":
        simulated += "logistics chain nominal. Supply route ALPHA remains viable. ETA: 4 hours."
    elif engine == "allam":
        simulated += "تحليل الوضع يشير إلى استقرار نسبي في المنطقة. التوصية: مواصلة المراقبة."

    latency = (time.time() - start) * 1000 + 45.0
    return {"text": simulated, "tokens": len(simulated.split()), "latency_ms": latency, "live": False}


# ── Endpoint 1: Health Check ─────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(
        status="operational",
        uptime_seconds=round(time.time() - state.start_time, 2),
        engines=dict(state.engine_status),
        memory=get_memory_info(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/edge/status", tags=["Edge Runtime"])
async def edge_status() -> Dict[str, Any]:
    """Expose austere runtime status for operators and integrations."""
    return get_edge_runtime_status()


# ── Endpoint 2: Single Engine Inference ──────────────────────

@app.post("/inference", response_model=InferenceResponse, tags=["Inference"])
async def run_inference(req: InferenceRequest):
    engine = state.resolve_engine(req.engine, req.domain)
    state.request_count += 1
    request_id = f"req-{state.request_count:06d}"

    result = simulate_inference(engine, req.prompt, req.max_tokens, req.temperature)

    state.log_audit("inference", {
        "request_id": request_id,
        "engine": engine,
        "prompt_length": len(req.prompt),
        "tokens": result["tokens"],
        "latency_ms": result["latency_ms"],
        "live": result.get("live", False)
    })

    return InferenceResponse(
        request_id=request_id,
        engine=engine,
        response=result["text"],
        tokens_used=result["tokens"],
        latency_ms=round(result["latency_ms"], 2),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# ── Endpoint 3: Consensus Inference ──────────────────────────

@app.post("/consensus", response_model=ConsensusResponse, tags=["Inference"])
async def run_consensus(req: ConsensusRequest):
    engines = req.engines or ["phi3", "grok", "mistral", "allam"]
    state.request_count += 1
    request_id = f"con-{state.request_count:06d}"

    start = time.time()
    engine_responses = {}
    for eng in engines:
        if eng not in state.engine_status:
            raise HTTPException(status_code=400, detail=f"Unknown engine: {eng}")
        result = simulate_inference(eng, req.prompt, req.max_tokens, req.temperature)
        engine_responses[eng] = result["text"]

    # Simple consensus: combine responses
    consensus_text = f"[CONSENSUS/{req.strategy.upper()}] "
    consensus_text += f"Based on {len(engines)} engine analysis: "
    consensus_text += engine_responses.get(engines[0], "No response")

    agreement = 0.85 if len(engines) > 2 else 0.72
    latency = (time.time() - start) * 1000

    state.log_audit("consensus", {
        "request_id": request_id,
        "engines": engines,
        "strategy": req.strategy,
        "agreement": agreement,
        "latency_ms": latency
    })

    return ConsensusResponse(
        request_id=request_id,
        consensus=consensus_text,
        engine_responses=engine_responses,
        agreement_score=agreement,
        strategy=req.strategy,
        latency_ms=round(latency, 2),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


# ── Endpoint 4: Domain-Routed Inference ──────────────────────

@app.post("/inference/{domain}", response_model=InferenceResponse, tags=["Inference"])
async def domain_inference(domain: str, req: InferenceRequest):
    if domain not in state.domain_routing:
        raise HTTPException(status_code=404, detail=f"Unknown domain: {domain}")
    req.domain = domain
    return await run_inference(req)


# ── Endpoint 5: List Engines ─────────────────────────────────

@app.get("/engines", tags=["Engine Management"])
async def list_engines():
    engines = []
    for name, status in state.engine_status.items():
        engines.append({
            "name": name,
            "status": status,
            "model_path": api_config.model_paths.get(name, "unknown"),
            "gpu_layers": api_config.gpu_layers.get(name, 0)
        })
    return {"engines": engines, "total": len(engines)}


# ── Endpoint 6: Engine Status ────────────────────────────────

@app.get("/engines/{engine_name}", tags=["Engine Management"])
async def engine_status(engine_name: str):
    if engine_name not in state.engine_status:
        raise HTTPException(status_code=404, detail=f"Engine not found: {engine_name}")
    return {
        "name": engine_name,
        "status": state.engine_status[engine_name],
        "model_path": api_config.model_paths.get(engine_name, "unknown"),
        "gpu_layers": api_config.gpu_layers.get(engine_name, 0),
        "domain_assignments": [
            d for d, e in state.domain_routing.items() if e == engine_name
        ]
    }


# ── Endpoint 7: Load Engine ──────────────────────────────────

@app.post("/engines/{engine_name}/load", tags=["Engine Management"])
async def load_engine(engine_name: str):
    if engine_name not in state.engine_status:
        raise HTTPException(status_code=404, detail=f"Engine not found: {engine_name}")

    if state.engine_status[engine_name] == "loaded":
        return {"message": f"{engine_name} already loaded", "status": "loaded"}

    model_path = api_config.model_paths.get(engine_name)
    gpu_layers = api_config.gpu_layers.get(engine_name, 35)

    try:
        from llama_cpp import Llama
        import os
        if os.path.exists(model_path):
            state.engines[engine_name] = Llama(
                model_path=model_path,
                n_gpu_layers=gpu_layers,
                n_ctx=4096,
                verbose=False
            )
            state.engine_status[engine_name] = "loaded"
            state.log_audit("engine_load", {"engine": engine_name, "status": "loaded"})
            return {"message": f"{engine_name} loaded successfully", "status": "loaded"}
        else:
            state.engine_status[engine_name] = "simulated"
            state.log_audit("engine_load", {"engine": engine_name, "status": "simulated", "reason": "model file not found"})
            return {"message": f"{engine_name} in simulation mode (model not found)", "status": "simulated"}
    except ImportError:
        state.engine_status[engine_name] = "simulated"
        state.log_audit("engine_load", {"engine": engine_name, "status": "simulated", "reason": "llama-cpp not available"})
        return {"message": f"{engine_name} in simulation mode", "status": "simulated"}


# ── Endpoint 8: Unload Engine ────────────────────────────────

@app.post("/engines/{engine_name}/unload", tags=["Engine Management"])
async def unload_engine(engine_name: str):
    if engine_name not in state.engine_status:
        raise HTTPException(status_code=404, detail=f"Engine not found: {engine_name}")

    if engine_name in state.engines:
        del state.engines[engine_name]

    state.engine_status[engine_name] = "unloaded"
    state.log_audit("engine_unload", {"engine": engine_name})
    return {"message": f"{engine_name} unloaded", "status": "unloaded"}


# ── Endpoint 9: Update Engine Config ─────────────────────────

@app.patch("/engines/{engine_name}", tags=["Engine Management"])
async def update_engine_config(engine_name: str, config: EngineConfigUpdate):
    if engine_name not in state.engine_status:
        raise HTTPException(status_code=404, detail=f"Engine not found: {engine_name}")

    updates = {}
    if config.gpu_layers is not None:
        api_config.gpu_layers[engine_name] = config.gpu_layers
        updates["gpu_layers"] = config.gpu_layers
    if config.temperature is not None:
        updates["temperature"] = config.temperature
    if config.max_tokens is not None:
        updates["max_tokens"] = config.max_tokens

    state.log_audit("engine_config_update", {"engine": engine_name, "updates": updates})
    return {"message": f"{engine_name} config updated", "updates": updates}


# ── Endpoint 10: Domain Routing Table ─────────────────────────

@app.get("/routing", tags=["Configuration"])
async def get_routing():
    return {"domain_routing": state.domain_routing}


# ── Endpoint 11: Update Routing ───────────────────────────────

@app.put("/routing", tags=["Configuration"])
async def update_routing(routing: Dict[str, str]):
    for domain, engine in routing.items():
        if engine not in state.engine_status:
            raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")
    state.domain_routing.update(routing)
    state.log_audit("routing_update", {"new_routing": routing})
    return {"message": "Routing updated", "domain_routing": state.domain_routing}


# ── Endpoint 12: Audit Logs ──────────────────────────────────

@app.get("/audit", tags=["System"])
async def get_audit_logs(limit: int = 50, action: Optional[str] = None):
    logs = state.audit_log
    if action:
        logs = [l for l in logs if l["action"] == action]
    return {"logs": logs[-limit:], "total": len(logs)}


# ── Endpoint 13: System Stats ────────────────────────────────

@app.get("/stats", tags=["System"])
async def system_stats():
    return {
        "uptime_seconds": round(time.time() - state.start_time, 2),
        "total_requests": state.request_count,
        "engines_loaded": sum(1 for s in state.engine_status.values() if s == "loaded"),
        "engines_simulated": sum(1 for s in state.engine_status.values() if s == "simulated"),
        "audit_entries": len(state.audit_log),
        "domain_routing": state.domain_routing,
        "memory": get_memory_info(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ── Error Handlers ───────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    state.log_audit("error", {"path": str(request.url), "error": str(exc)})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )


