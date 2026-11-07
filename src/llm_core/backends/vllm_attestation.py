"""
Attestation verification for core-tier vLLM strategist nodes.

Tactical context: production inference must present confidential-computing
evidence (NVIDIA CC, Intel TDX, AMD SEV-SNP) before S3M will route council traffic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging

logger = logging.getLogger("s3m.backends.vllm.attestation")


class AttestationVerifier(ABC):
    """Pluggable verifier for opaque attestation documents from the inference server."""

    @abstractmethod
    def verify(self, attestation_blob: bytes) -> bool:
        """Return True when attestation evidence is acceptable for the deployment mode."""


class NullVerifier(AttestationVerifier):
    """
    Lab-only verifier that accepts any non-empty blob.

    Must never be used when ``lab_mode`` is false; VllmBackend enforces that pairing.
    """

    def verify(self, attestation_blob: bytes) -> bool:
        if not attestation_blob:
            logger.warning("NullVerifier rejected empty attestation blob")
            return False
        return True


class AttestationError(RuntimeError):
    """Raised when attestation is missing or fails verification in production."""
