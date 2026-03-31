"""
S3M Security, Interoperability & NATO Compliance
Cross-cutting security layer wrapping the entire 6-layer stack.

Subsystems:
- Middleware: Zero-trust auth, rate limiting, input sanitization, CORS lockdown
- Crypto: AES-256 encryption at rest, tamper-evident audit log, classification banners
- Interop: DIS (IEEE-1278.1), C2SIM (SISO), BML protocol adapters for NATO/GCC coalition ops
- Compliance: Self-assessment security checks, vulnerability scanning, LLM-generated reports

Design: Middleware wrapping, not rewriting. Phase 10 intercepts at the FastAPI level.
All previous layer code remains untouched.
"""

from src.security.airgap_verifier import AirGapVerifier
from src.security.compliance import (
    ComplianceChecker,
    SecurityReportGenerator,
    VulnerabilityScanner,
)
from src.security.crypto import ClassificationBanner, DataEncryptor, SecureAuditLog
from src.security.input_validator import InputValidator
from src.security.interop import BMLAdapter, C2SIMAdapter, DISAdapter, InteropManager
from src.security.middleware import SecurityMiddleware

__all__ = [
    "SecurityMiddleware",
    "InputValidator",
    "AirGapVerifier",
    "DataEncryptor",
    "SecureAuditLog",
    "ClassificationBanner",
    "DISAdapter",
    "C2SIMAdapter",
    "BMLAdapter",
    "InteropManager",
    "ComplianceChecker",
    "VulnerabilityScanner",
    "SecurityReportGenerator",
]
