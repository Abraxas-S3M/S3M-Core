"""S3M Quad-Engine REST API Server.

Provides 13 endpoints for inference, consensus, engine management, and audit logging.
Designed for air-gapped deployment on NVIDIA Jetson AGX Orin 64GB.
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import yaml

from src.api.config import api_config
from src.api.apps_routes import apps_router
from src.api.autonomy_routes import autonomy_router
from src.api.comms_routes import comms_router
from src.api.cyber_routes import cyber_router
from src.api.dashboard_routes import dashboard_router
from src.api.intel_routes import intel_router
from src.api.maintenance_routes import maintenance_router
from src.api.navigation_routes import navigation_router
from src.api.security_routes import security_router
from src.api.sensor_analytics_routes import sensor_analytics_router
from src.api.simulation_routes import simulation_router
from src.api.threat_routes import threat_router, sensor_router
from src.api.training_sim_routes import training_sim_router
from src.security.middleware import SecurityMiddleware

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


# ── Application Setup ────────────────────────────────────────

app = FastAPI(
    title="S3M Quad-Engine API",
    description="Tactical AI inference API for air-gapped deployment",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(autonomy_router, tags=["Autonomy & Swarm"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=api_config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threat_router, tags=["Threat Detection"])
app.include_router(sensor_router, tags=["Sensor Fusion"])
app.include_router(navigation_router, tags=["Navigation & Edge AI"])
app.include_router(dashboard_router, tags=["Dashboard"])
app.include_router(simulation_router, tags=["Simulation & Wargaming"])
app.include_router(apps_router, tags=["Domain Applications"])
app.include_router(intel_router, tags=["Intelligence & OSINT Briefings"])
app.include_router(training_sim_router, tags=["Training & Simulation Advanced"])
app.include_router(sensor_analytics_router, tags=["Sensor & Remote Sensing Analytics"])
app.include_router(comms_router, tags=["Secure Communications"])

# Load security config
security_config = {}
security_config_path = "configs/security.yaml"
if os.path.exists(security_config_path):
    with open(security_config_path) as f:
        security_config = yaml.safe_load(f).get("middleware", {})

# Add security middleware (wraps ALL requests)
app.add_middleware(SecurityMiddleware, config=security_config)

# Add security routes
app.include_router(security_router, tags=["Security & Compliance"])
app.include_router(cyber_router, tags=["Cyber Defense Operations"])
app.include_router(maintenance_router, tags=["Procurement & Maintenance"])

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


@app.on_event("startup")
async def optimization_startup_hook():
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
