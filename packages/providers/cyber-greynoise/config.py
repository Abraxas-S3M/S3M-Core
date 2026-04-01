"""GreyNoise provider configuration."""

from dataclasses import dataclass


@dataclass
class GreyNoiseConfig:
    base_url: str = "https://api.greynoise.io"
    community_endpoint: str = "/v3/community"
    rate_limit_rpm: int = 3
    daily_quota: int = 50
