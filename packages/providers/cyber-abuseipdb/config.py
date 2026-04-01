"""AbuseIPDB provider configuration."""

from dataclasses import dataclass, field


@dataclass
class AbuseIPDBConfig:
    base_url: str = "https://api.abuseipdb.com/api/v2"
    rate_limit_rpm: int = 20
    daily_quota: int = 1000
    default_max_age_days: int = 90
    confidence_threshold: int = 50
    high_confidence_threshold: int = 80
    abuse_category_names: dict[int, str] = field(default_factory=lambda: {
        1: "DNS Compromise", 2: "DNS Poisoning", 3: "Fraud Orders", 4: "DDoS Attack", 5: "FTP Brute-Force",
        7: "Ping of Death", 9: "Open Proxy", 10: "Web Spam", 11: "Email Spam", 14: "Port Scan", 15: "Hacking",
        18: "Brute-Force", 19: "Bad Web Bot", 20: "Exploited Host", 21: "Web App Attack", 22: "SSH", 23: "IoT Targeted",
    })
