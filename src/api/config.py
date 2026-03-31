"""API Configuration for S3M Quad-Engine System."""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class APIConfig:
    """Configuration for the S3M API server."""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    debug: bool = False
    api_key: Optional[str] = None
    max_tokens_default: int = 512
    temperature_default: float = 0.7
    cors_origins: list = field(default_factory=lambda: ["*"])

    # Engine model paths
    model_paths: Dict[str, str] = field(default_factory=lambda: {
        "phi3": "models/phi-3-mini-4k-instruct.Q4_K_M.gguf",
        "grok": "models/grok-8b.Q4_K_M.gguf",
        "mistral": "models/mistral-7b-instruct-v0.3.Q4_K_M.gguf",
        "allam": "models/allam-7b-instruct.Q4_K_M.gguf"
    })

    # Engine GPU layers
    gpu_layers: Dict[str, int] = field(default_factory=lambda: {
        "phi3": 35,
        "grok": 33,
        "mistral": 35,
        "allam": 35
    })

    # Domain routing defaults
    domain_routing: Dict[str, str] = field(default_factory=lambda: {
        "tactical": "phi3",
        "intelligence": "grok",
        "logistics": "mistral",
        "arabic": "allam",
        "general": "phi3"
    })


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    enabled: bool = True
    requests_per_minute: int = 60
    burst_size: int = 10


# Global config instance
api_config = APIConfig()
rate_limit_config = RateLimitConfig()
