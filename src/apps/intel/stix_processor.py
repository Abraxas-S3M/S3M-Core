"""Local STIX 2.1 processing for tactical watchlist exchange.

This module intentionally performs offline bundle creation/import only and
does not call OpenCTI or any external service endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import stix2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class STIXProcessor:
    """Create and parse STIX 2.1 bundles for local watchlist workflows."""

    @staticmethod
    def _stix2_module():
        try:
            return importlib.import_module("stix2")
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("stix2 is required for local STIX processing") from exc

    @staticmethod
    def _entity_category_from_labels(object_type: str, labels: list[str]) -> str:
        lowered = {str(label).strip().lower() for label in labels if label}
        for known in ("persons", "organizations", "vessels", "vehicles", "sites"):
            if known in lowered:
                return known
        if object_type == "threat-actor":
            return "organizations"
        if object_type == "indicator":
            return "sites"
        return "organizations"

    @staticmethod
    def _default_indicator_pattern(name: str, category: str) -> str:
        # Tactical context: the local indicator anchor keeps non-cyber entities
        # searchable in STIX-compliant tooling without external enrichment.
        safe_name = name.replace("'", "\\'")
        return f"[x-s3m-{category}:name = '{safe_name}']"

    @staticmethod
    def _to_raw(obj: Any) -> dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "serialize"):
            return json.loads(obj.serialize())
        return dict(obj)

    def create_indicator(self, name: str, pattern: str, labels: list[str]) -> "stix2.Indicator":
        """Build a STIX indicator for local surveillance watchlist matching."""
        normalized_name = str(name).strip()
        normalized_pattern = str(pattern).strip()
        normalized_labels = [str(label).strip() for label in labels if str(label).strip()]
        if not normalized_name:
            raise ValueError("name is required")
        if not normalized_pattern:
            raise ValueError("pattern is required")
        if not normalized_labels:
            raise ValueError("at least one label is required")

        stix2 = self._stix2_module()
        return stix2.Indicator(
            name=normalized_name,
            pattern=normalized_pattern,
            pattern_type="stix",
            labels=normalized_labels,
            valid_from=_utc_now_iso(),
            allow_custom=True,
        )

    def create_threat_actor(
        self,
        name: str,
        aliases: list[str] | None,
        country: str | None,
    ) -> "stix2.ThreatActor":
        """Build a STIX threat actor record for tactical person/org watchlists."""
        normalized_name = str(name).strip()
        if not normalized_name:
            raise ValueError("name is required")

        stix2 = self._stix2_module()
        cleaned_aliases = [str(alias).strip() for alias in aliases or [] if str(alias).strip()]
        normalized_country = str(country or "").strip()
        return stix2.ThreatActor(
            name=normalized_name,
            aliases=cleaned_aliases,
            threat_actor_types=["unknown"],
            labels=["watchlist", "organizations"],
            allow_custom=True,
            x_mil_country=normalized_country,
        )

    def bundle_watchlist(self, entities: list[dict[str, Any]]) -> "stix2.Bundle":
        """Create a STIX 2.1 bundle from local watchlist entities."""
        stix2 = self._stix2_module()
        objects: list[Any] = []

        for raw_entity in entities:
            category = str(raw_entity.get("category", "")).strip().lower()
            if category not in {"persons", "organizations", "vessels", "vehicles", "sites"}:
                continue

            entity_id = str(raw_entity.get("id", "")).strip()
            name = str(raw_entity.get("name", "")).strip()
            aliases = raw_entity.get("aliases") or []
            country = str(raw_entity.get("country", "")).strip()
            labels = [str(label).strip() for label in (raw_entity.get("labels") or []) if str(label).strip()]
            if "watchlist" not in labels:
                labels.insert(0, "watchlist")
            if category not in labels:
                labels.append(category)

            if not name:
                continue

            if category in {"persons", "organizations"}:
                actor = stix2.ThreatActor(
                    name=name,
                    aliases=[str(alias).strip() for alias in aliases if str(alias).strip()],
                    threat_actor_types=["unknown"],
                    labels=labels,
                    allow_custom=True,
                    x_mil_country=country,
                    x_mil_watchlist_category=category,
                    x_mil_watchlist_id=entity_id,
                )
                objects.append(actor)
            else:
                pattern = str(raw_entity.get("pattern", "")).strip() or self._default_indicator_pattern(name, category)
                indicator = stix2.Indicator(
                    name=name,
                    pattern=pattern,
                    pattern_type="stix",
                    labels=labels,
                    valid_from=_utc_now_iso(),
                    allow_custom=True,
                    x_mil_country=country,
                    x_mil_watchlist_category=category,
                    x_mil_watchlist_id=entity_id,
                )
                objects.append(indicator)

        return stix2.Bundle(objects=objects, allow_custom=True)

    def import_bundle(self, json_path: str | Path) -> list[dict[str, Any]]:
        """Import a STIX bundle file into normalized local watchlist entities."""
        stix2 = self._stix2_module()
        payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
        bundle = stix2.parse(payload, allow_custom=True)
        raw_bundle = self._to_raw(bundle)
        if raw_bundle.get("type") != "bundle":
            raise ValueError("json_path must contain a STIX bundle")

        imported: list[dict[str, Any]] = []
        for obj in bundle.objects:
            raw = self._to_raw(obj)
            object_type = str(raw.get("type", "")).strip()
            labels = [str(label).strip() for label in raw.get("labels", []) if str(label).strip()]
            category = str(raw.get("x_mil_watchlist_category", "")).strip().lower() or self._entity_category_from_labels(
                object_type, labels
            )
            if category not in {"persons", "organizations", "vessels", "vehicles", "sites"}:
                continue

            imported.append(
                {
                    "id": str(raw.get("x_mil_watchlist_id") or raw.get("id") or "").strip(),
                    "category": category,
                    "name": str(raw.get("name", "")).strip(),
                    "aliases": [str(alias).strip() for alias in raw.get("aliases", []) if str(alias).strip()],
                    "country": str(raw.get("x_mil_country", "")).strip(),
                    "labels": labels,
                    "pattern": str(raw.get("pattern", "")).strip(),
                    "details": {
                        "stix_id": str(raw.get("id", "")).strip(),
                        "stix_type": object_type,
                    },
                }
            )

        return imported
