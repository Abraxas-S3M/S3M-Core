"""PII-safe normalization helpers for Elm responses."""

from __future__ import annotations

from typing import Any


class ElmNormalizer:
    def normalize_identity_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "verified": bool(result.get("verified", False)),
            "nationality": result.get("nationality", ""),
            "status": result.get("status", "unknown"),
        }

    def normalize_vehicle_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "registered": bool(result.get("registered", False)),
            "owner_type": result.get("owner_type", "unknown"),
            "vehicle_type": result.get("vehicle_type", "unknown"),
        }
