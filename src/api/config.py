"""Environment-driven API configuration for S3M Quad-Engine System."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI

from src.command.mission_command_engine import MissionCommandEngine

LOGGER = logging.getLogger(__name__)


class DeploymentMode(str, Enum):
    """Supported deployment targets."""

    JETSON_EDGE = "jetson_edge"
    CLOUD_CPU_DEMO = "cloud_cpu_demo"
    GPU_CLUSTER = "gpu_cluster"


def _load_dotenv_if_present(env_file: str = ".env") -> None:
    """Load .env key-values unless already defined in process environment."""
    env_path = Path(env_file)
    if not env_path.exists() or not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _parse_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"true", "1", "yes", "on"}


def _parse_int(val: Optional[str], default: int) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _parse_float(val: Optional[str], default: float) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _parse_cors(val: Optional[str]) -> List[str]:
    if val is None:
        return []
    stripped = val.strip()
    if not stripped:
        return []
    return [origin.strip() for origin in stripped.split(",") if origin.strip()]


def _resolve_deployment_mode(raw_mode: Optional[str]) -> DeploymentMode:
    mode_text = (raw_mode or DeploymentMode.JETSON_EDGE.value).strip().lower()
    try:
        return DeploymentMode(mode_text)
    except ValueError:
        LOGGER.warning(
            "Unknown DEPLOYMENT_MODE '%s', defaulting to '%s'",
            raw_mode,
            DeploymentMode.JETSON_EDGE.value,
        )
        return DeploymentMode.JETSON_EDGE


def _hardware_has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _detect_device(forced_device: Optional[str], mode: DeploymentMode) -> str:
    """Resolve tactical runtime device using policy + hardware capability."""
    if mode == DeploymentMode.CLOUD_CPU_DEMO:
        return "cpu"

    forced = (forced_device or "auto").strip().lower()
    if forced == "cpu":
        return "cpu"
    if forced == "cuda":
        return "cuda" if _hardware_has_cuda() else "cpu"
    return "cuda" if _hardware_has_cuda() else "cpu"


@dataclass
class APIConfig:
    """Configuration for the S3M API server."""

    # Deployment
    deployment_mode: DeploymentMode = DeploymentMode.JETSON_EDGE
    device: str = "cpu"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    log_level: str = "info"
    debug: bool = False

    # Auth
    api_key: Optional[str] = None
    auth_enabled: bool = False

    # CORS
    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    # Inference defaults
    max_tokens_default: int = 512
    temperature_default: float = 0.7

    # Runtime paths
    model_dir: str = "models"
    data_dir: str = "data"
    checkpoint_dir: str = "data/checkpoints"

    # CPU threading defaults
    omp_num_threads: int = 8
    mkl_num_threads: int = 8

    # Engine model paths
    model_paths: Dict[str, str] = field(default_factory=lambda: {
        "phi3": "models/phi-3-mini-4k-instruct.Q4_K_M.gguf",
        "grok": "models/grok-8b.Q4_K_M.gguf",
        "mistral": "models/mistral-7b-instruct-v0.3.Q4_K_M.gguf",
        "allam": "models/allam-7b-instruct.Q4_K_M.gguf",
    })

    # Engine GPU layers
    gpu_layers: Dict[str, int] = field(default_factory=lambda: {
        "phi3": 35,
        "grok": 33,
        "mistral": 35,
        "allam": 35,
    })

    # Domain routing defaults
    domain_routing: Dict[str, str] = field(default_factory=lambda: {
        "tactical": "phi3",
        "intelligence": "grok",
        "logistics": "mistral",
        "arabic": "allam",
        "general": "phi3",
    })

    def is_cpu_mode(self) -> bool:
        return self.device == "cpu"

    def is_cloud_demo(self) -> bool:
        return self.deployment_mode == DeploymentMode.CLOUD_CPU_DEMO


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    enabled: bool = True
    requests_per_minute: int = 60
    burst_size: int = 10


def _build_config() -> APIConfig:
    """Build API config from .env + process environment."""
    _load_dotenv_if_present(".env")

    deployment_mode = _resolve_deployment_mode(os.environ.get("DEPLOYMENT_MODE", "jetson_edge"))

    cors_default = "" if deployment_mode == DeploymentMode.CLOUD_CPU_DEMO else "*"
    cors_origins = _parse_cors(os.environ.get("CORS_ORIGINS", cors_default))

    auth_default = deployment_mode == DeploymentMode.CLOUD_CPU_DEMO
    auth_enabled = _parse_bool(os.environ.get("S3M_AUTH_ENABLED"), default=auth_default)

    cfg = APIConfig(
        deployment_mode=deployment_mode,
        device=_detect_device(os.environ.get("S3M_DEVICE", "auto"), deployment_mode),
        host=os.environ.get("S3M_HOST", "0.0.0.0"),
        port=_parse_int(os.environ.get("S3M_PORT"), 8080),
        workers=_parse_int(os.environ.get("S3M_WORKERS"), 1),
        log_level=os.environ.get("S3M_LOG_LEVEL", "info"),
        debug=_parse_bool(os.environ.get("S3M_DEBUG"), default=False),
        api_key=os.environ.get("S3M_API_KEY"),
        auth_enabled=auth_enabled,
        cors_origins=cors_origins,
        max_tokens_default=_parse_int(os.environ.get("S3M_MAX_TOKENS"), 512),
        temperature_default=_parse_float(os.environ.get("S3M_TEMPERATURE"), 0.7),
        omp_num_threads=_parse_int(os.environ.get("OMP_NUM_THREADS"), 8),
        mkl_num_threads=_parse_int(os.environ.get("MKL_NUM_THREADS"), 8),
        model_dir=os.environ.get("S3M_MODEL_DIR", "models"),
        data_dir=os.environ.get("S3M_DATA_DIR", "data"),
        checkpoint_dir=os.environ.get("S3M_CHECKPOINT_DIR", "data/checkpoints"),
    )

    # Tactical cloud demo policy: always CPU-only for predictable public runtime.
    if cfg.is_cpu_mode():
        cfg.gpu_layers = {engine: 0 for engine in cfg.gpu_layers}

    return cfg


def get_device() -> str:
    """Return resolved compute device ("cuda" or "cpu")."""
    return api_config.device


# Global config instances (backward compatibility).
api_config = _build_config()
rate_limit_config = RateLimitConfig()


@asynccontextmanager
async def mission_command_lifespan(app: FastAPI):
    """
    FastAPI lifespan hook that runs Mission Command Engine in background.

    Tactical context:
    Keeps command-and-control event processing active throughout API uptime,
    then performs orderly shutdown to preserve operational state consistency.
    """
    mce = MissionCommandEngine()
    app.state.mce = mce
    mce_task = asyncio.create_task(mce.start(), name="mission-command-engine")
    try:
        yield
    finally:
        mce.stop()
        if not mce_task.done():
            mce_task.cancel()
        try:
            await mce_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - defensive shutdown logging
            LOGGER.warning("Mission Command Engine shutdown warning: %s", exc)
