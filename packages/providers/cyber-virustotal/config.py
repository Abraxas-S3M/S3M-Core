"""VirusTotal provider configuration."""

from dataclasses import dataclass


@dataclass
class VirusTotalConfig:
    base_url: str = "https://www.virustotal.com/api/v3"
    rate_limit_rpm: int = 4
    daily_quota: int = 500
    malicious_threshold: int = 3
