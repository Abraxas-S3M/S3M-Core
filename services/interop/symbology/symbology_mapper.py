"""High-level symbology mapper for GUI, DIS, and CoT tracks."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.interop.models import DISEntityType
from services.interop.symbology.sidc_generator import SIDCGenerator


class SymbologyMapper:
    """Resolves the best available SIDC representation for S3M tracks."""

    @classmethod
    def map_track_symbology(cls, track: Dict[str, Any]) -> str:
        """Return SIDC for a generic track payload."""

        if not isinstance(track, dict):
            return SIDCGenerator.generate("unknown", "land", "UNKNOWN")

        existing_sidc = track.get("sidc")
        if SIDCGenerator.is_valid_sidc(existing_sidc):
            return str(existing_sidc)

        dis_type = cls._extract_dis_type(track)
        force_id = cls._extract_force_id(track)
        if dis_type is not None:
            return SIDCGenerator.from_dis_entity_type(dis_type=dis_type, force_id=force_id)

        affiliation = cls._extract_affiliation(track)
        entity_type = cls._extract_entity_type(track)
        domain = cls._extract_domain(track, entity_type=entity_type)

        if entity_type:
            return SIDCGenerator.generate(
                affiliation=affiliation,
                domain=domain,
                entity_type=entity_type,
            )
        return SIDCGenerator.generate(
            affiliation=affiliation,
            domain=domain,
            entity_type="UNKNOWN",
        )

    @classmethod
    def enrich_gui_track(cls, track: Any) -> Any:
        """Fill missing/invalid SIDC for GUI threat tracks."""

        if track is None:
            return track
        existing_sidc = getattr(track, "sidc", None)
        if SIDCGenerator.is_valid_sidc(existing_sidc):
            return track

        payload = {
            "sidc": existing_sidc,
            "domain": getattr(track, "domain", None),
            "entity_type": getattr(track, "summary", None),
            "type": getattr(track, "summary", None),
            "affiliation": getattr(track, "affiliation", None),
            "identity": getattr(track, "identity", None),
        }
        track.sidc = cls.map_track_symbology(payload)
        return track

    @staticmethod
    def _extract_dis_type(track: Dict[str, Any]) -> Optional[DISEntityType]:
        candidate = track.get("dis_entity_type")
        if isinstance(candidate, DISEntityType):
            return candidate
        if isinstance(candidate, dict):
            try:
                return DISEntityType(
                    kind=int(candidate.get("kind", 0)),
                    domain=int(candidate.get("domain", 0)),
                    country=int(candidate.get("country", 0)),
                    category=int(candidate.get("category", 0)),
                    subcategory=int(candidate.get("subcategory", 0)),
                    specific=int(candidate.get("specific", 0)),
                    extra=int(candidate.get("extra", 0)),
                )
            except Exception:
                return None

        dis_fields = ("kind", "domain", "country", "category", "subcategory")
        if any(field in track for field in dis_fields):
            try:
                return DISEntityType(
                    kind=int(track.get("kind", 0)),
                    domain=int(track.get("domain", 0)),
                    country=int(track.get("country", 0)),
                    category=int(track.get("category", 0)),
                    subcategory=int(track.get("subcategory", 0)),
                    specific=int(track.get("specific", 0)),
                    extra=int(track.get("extra", 0)),
                )
            except Exception:
                return None
        return None

    @staticmethod
    def _extract_force_id(track: Dict[str, Any]) -> int:
        force_id = track.get("force_id", track.get("forceId", 3))
        try:
            return int(force_id)
        except Exception:
            return 3

    @staticmethod
    def _extract_entity_type(track: Dict[str, Any]) -> str:
        for key in ("entity_type", "entityType", "type", "classification", "summary"):
            value = track.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return "UNKNOWN"

    @staticmethod
    def _extract_affiliation(track: Dict[str, Any]) -> str:
        for key in ("affiliation", "allegiance", "identity", "side"):
            raw = str(track.get(key, "")).strip().lower()
            if raw:
                return raw
        entity_type = str(track.get("entity_type", track.get("type", ""))).upper()
        if entity_type.startswith("FRIENDLY_"):
            return "friendly"
        if entity_type.startswith("ENEMY_"):
            return "hostile"
        return "unknown"

    @staticmethod
    def _extract_domain(track: Dict[str, Any], entity_type: str) -> str:
        raw_domain = str(track.get("domain", "")).strip().lower()
        if raw_domain in {"air", "land", "surface", "subsurface", "space"}:
            return raw_domain
        if raw_domain in {"sea", "maritime"}:
            return "surface"
        if raw_domain in {"ground", "kinetic"}:
            return "land"

        descriptor = str(entity_type or "").lower()
        if any(token in descriptor for token in ("uav", "aircraft", "air", "missile")):
            return "air"
        if any(token in descriptor for token in ("ship", "vessel", "boat", "sea", "maritime")):
            return "surface"
        if any(token in descriptor for token in ("subsurface", "submarine", "sub")):
            return "subsurface"
        if any(token in descriptor for token in ("space", "satellite", "orbital")):
            return "space"
        return "land"
