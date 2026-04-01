"""Normalization and sovereign markings for NDMC official data."""

from __future__ import annotations

from typing import Any


class SovereignNDMCNormalizer:
    def add_government_marking(self, observation: dict[str, Any]) -> dict[str, Any]:
        out = dict(observation)
        out["classification"] = "SAUDI_GOVERNMENT_OFFICIAL"
        out["handling"] = "Official Use — GCC redistribution with approval"
        return out

    def normalize_official_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        out = self.add_government_marking(alert)
        out["alert_ar"] = str(out.get("alert_ar", "")).strip()
        out["alert_en"] = str(out.get("alert_en", "")).strip()
        out["authority"] = out.get("authority", "NCM")
        return out

    def normalize_military_advisory(self, advisory: dict[str, Any]) -> dict[str, Any]:
        out = self.add_government_marking(advisory)
        out.setdefault("conditions_ar", "")
        out.setdefault("conditions_en", "")
        out.setdefault("operational_impact", {})
        return out
