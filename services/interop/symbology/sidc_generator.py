"""MIL-STD-2525D SIDC generation for coalition track symbology."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from src.security.interop.dis_adapter import DIS_ENTITY_MAP as _DIS_ENTITY_MAP
except Exception:  # pragma: no cover - fallback for minimal environments
    _DIS_ENTITY_MAP: Dict[str, Dict[str, int]] = {
        "FRIENDLY_UAV": {"kind": 1, "domain": 2, "country": 178, "category": 1, "subcategory": 0},
        "FRIENDLY_UGV": {"kind": 1, "domain": 1, "country": 178, "category": 1, "subcategory": 0},
        "FRIENDLY_SHIP": {"kind": 1, "domain": 3, "country": 178, "category": 1, "subcategory": 0},
        "ENEMY_UAV": {"kind": 1, "domain": 2, "country": 0, "category": 1, "subcategory": 0},
        "ENEMY_UGV": {"kind": 1, "domain": 1, "country": 0, "category": 1, "subcategory": 0},
        "ENEMY_SHIP": {"kind": 1, "domain": 3, "country": 0, "category": 1, "subcategory": 0},
        "ENEMY_INFANTRY": {"kind": 3, "domain": 1, "country": 0, "category": 1, "subcategory": 0},
        "CIVILIAN": {"kind": 3, "domain": 1, "country": 0, "category": 0, "subcategory": 0},
        "OBSTACLE": {"kind": 2, "domain": 1, "country": 0, "category": 0, "subcategory": 0},
        "WAYPOINT": {"kind": 9, "domain": 0, "country": 0, "category": 0, "subcategory": 0},
        "BASE": {"kind": 1, "domain": 1, "country": 178, "category": 2, "subcategory": 0},
        "UNKNOWN": {"kind": 0, "domain": 0, "country": 0, "category": 0, "subcategory": 0},
    }


class SIDCGenerator:
    """Builds deterministic 20-digit SIDCs for S3M tactical entities."""

    _AFFILIATION_MAP: Dict[str, str] = {
        "friendly": "3",
        "assumed_friend": "2",
        "hostile": "6",
        "suspect": "5",
        "neutral": "4",
        "unknown": "1",
        "pending": "0",
    }

    _DOMAIN_TO_SYMBOL_SET: Dict[str, str] = {
        "air": "01",
        "land": "10",
        "surface": "30",
        "subsurface": "40",
        "space": "60",
    }

    _S3M_ENTITY_TABLE: Dict[str, Dict[str, str]] = {
        "FRIENDLY_UAV": {"symbol_set": "01", "entity": "01", "type": "01"},
        "FRIENDLY_UGV": {"symbol_set": "10", "entity": "12", "type": "11"},
        "FRIENDLY_SHIP": {"symbol_set": "30", "entity": "01", "type": "02"},
        "ENEMY_UAV": {"symbol_set": "01", "entity": "01", "type": "01"},
        "ENEMY_UGV": {"symbol_set": "10", "entity": "12", "type": "11"},
        "ENEMY_SHIP": {"symbol_set": "30", "entity": "01", "type": "02"},
        "ENEMY_INFANTRY": {"symbol_set": "10", "entity": "12", "type": "01"},
        "CIVILIAN": {"symbol_set": "10", "entity": "01", "type": "00"},
        "OBSTACLE": {"symbol_set": "15", "entity": "01", "type": "01"},
        "WAYPOINT": {"symbol_set": "10", "entity": "22", "type": "00"},
        "BASE": {"symbol_set": "10", "entity": "21", "type": "01"},
        "UNKNOWN": {"symbol_set": "10", "entity": "00", "type": "00"},
    }

    _AFFILIATION_ALIASES: Dict[str, str] = {
        "friend": "friendly",
        "blue": "friendly",
        "ally": "friendly",
        "allied": "friendly",
        "own": "friendly",
        "enemy": "hostile",
        "adversary": "hostile",
        "red": "hostile",
        "unfriendly": "hostile",
    }

    _FORCE_ID_TO_AFFILIATION: Dict[int, str] = {
        1: "friendly",
        2: "hostile",
        3: "neutral",
    }

    _SYMBOL_SET_TO_DOMAIN: Dict[str, str] = {
        "01": "air",
        "10": "land",
        "15": "land",
        "30": "surface",
        "40": "subsurface",
        "60": "space",
    }

    _DIS_DOMAIN_MAP: Dict[int, str] = {
        0: "land",
        1: "land",
        2: "air",
        3: "surface",
        4: "subsurface",
        5: "space",
    }

    _DEFAULT_ENTITY_CODES: Dict[str, Dict[str, str]] = {
        "01": {"entity": "01", "type": "00"},
        "10": {"entity": "12", "type": "00"},
        "15": {"entity": "01", "type": "00"},
        "30": {"entity": "01", "type": "00"},
        "40": {"entity": "01", "type": "00"},
        "60": {"entity": "01", "type": "00"},
    }

    _COT_AFFILIATION_TO_S3M: Dict[str, str] = {
        "f": "friendly",
        "a": "assumed_friend",
        "h": "hostile",
        "s": "suspect",
        "n": "neutral",
        "u": "unknown",
        "p": "pending",
    }

    _S3M_AFFILIATION_TO_COT: Dict[str, str] = {
        "0": "p",
        "1": "u",
        "2": "a",
        "3": "f",
        "4": "n",
        "5": "s",
        "6": "h",
    }

    _COT_DOMAIN_TO_S3M: Dict[str, str] = {
        "a": "air",
        "g": "land",
        "s": "surface",
        "u": "subsurface",
        "p": "space",
    }

    _S3M_DOMAIN_TO_COT: Dict[str, str] = {
        "air": "a",
        "land": "g",
        "surface": "s",
        "subsurface": "u",
        "space": "p",
    }

    _DIS_ENTITY_MAP: Dict[str, Dict[str, int]] = _DIS_ENTITY_MAP

    _DIS_ENTITY_LOOKUP: Dict[tuple[int, int, int, int, int], str] = {
        (
            int(payload["kind"]),
            int(payload["domain"]),
            int(payload["country"]),
            int(payload["category"]),
            int(payload.get("subcategory", 0)),
        ): key
        for key, payload in _DIS_ENTITY_MAP.items()
    }

    @classmethod
    def generate(cls, affiliation: str, domain: str, entity_type: str, **kwargs: Any) -> str:
        """Generate a 20-character MIL-STD-2525D SIDC."""

        normalized_affiliation = cls._normalize_affiliation(affiliation)
        affiliation_code = cls._AFFILIATION_MAP.get(normalized_affiliation, "1")
        normalized_key = cls._normalize_entity_key(entity_type)
        template = cls._S3M_ENTITY_TABLE.get(normalized_key)
        normalized_domain = cls._normalize_domain(domain)

        if template is not None:
            symbol_set = template["symbol_set"]
            entity = template["entity"]
            entity_type_code = template["type"]
            entity_subtype = template.get("subtype", "00")
        else:
            symbol_set = cls._DOMAIN_TO_SYMBOL_SET.get(normalized_domain, "10")
            defaults = cls._DEFAULT_ENTITY_CODES.get(symbol_set, {"entity": "00", "type": "00"})
            entity = defaults["entity"]
            entity_type_code = defaults["type"]
            entity_subtype = "00"

        status = cls._normalize_status(kwargs.get("status"), kwargs.get("planned"))
        hq_tf_dummy = cls._one_digit(kwargs.get("hq_tf_dummy"), default="0")
        amplifier = cls._two_digit(kwargs.get("amplifier"), default="00")
        modifier_1 = cls._two_digit(kwargs.get("modifier_1"), default="00")
        modifier_2 = cls._two_digit(kwargs.get("modifier_2"), default="00")
        reserved = cls._one_digit(kwargs.get("reserved"), default="0")

        sidc = (
            "10"
            + affiliation_code
            + cls._two_digit(symbol_set, default="10")
            + cls._two_digit(entity, default="00")
            + cls._two_digit(entity_type_code, default="00")
            + cls._two_digit(entity_subtype, default="00")
            + modifier_1
            + modifier_2
            + status
            + hq_tf_dummy
            + amplifier
            + reserved
        )
        if cls.is_valid_sidc(sidc):
            return sidc
        return "10110000000000000000"

    @classmethod
    def from_dis_entity_type(cls, dis_type: Any, force_id: int) -> str:
        """Map DIS entity type fields into a SIDC."""

        kind = int(getattr(dis_type, "kind", 0))
        domain = int(getattr(dis_type, "domain", 0))
        country = int(getattr(dis_type, "country", 0))
        category = int(getattr(dis_type, "category", 0))
        subcategory = int(getattr(dis_type, "subcategory", 0))

        key_candidates = [
            (kind, domain, country, category, subcategory),
            (kind, domain, 0, category, subcategory),
            (kind, domain, 178, category, subcategory),
        ]
        entity_key = next(
            (
                cls._DIS_ENTITY_LOOKUP[candidate]
                for candidate in key_candidates
                if candidate in cls._DIS_ENTITY_LOOKUP
            ),
            "UNKNOWN",
        )
        affiliation = cls._resolve_dis_affiliation(entity_key, force_id=force_id, country=country)
        inferred_domain = cls._DIS_DOMAIN_MAP.get(domain, "land")
        return cls.generate(
            affiliation=affiliation,
            domain=inferred_domain,
            entity_type=entity_key,
        )

    @classmethod
    def from_cot_type(cls, cot_type_string: str) -> str:
        """Map a CoT type tree string to a SIDC."""

        normalized = str(cot_type_string or "").strip().lower()
        if not normalized:
            return cls.generate(affiliation="unknown", domain="land", entity_type="UNKNOWN")

        tokens = [token for token in normalized.split("-") if token]
        cot_domain = tokens[0][0] if tokens else "g"
        cot_affiliation = tokens[1][0] if len(tokens) > 1 else "u"

        domain = cls._COT_DOMAIN_TO_S3M.get(cot_domain, "land")
        affiliation = cls._COT_AFFILIATION_TO_S3M.get(cot_affiliation, "unknown")

        if domain == "air" and affiliation in {"friendly", "assumed_friend"}:
            entity_type = "FRIENDLY_UAV"
        elif domain == "air" and affiliation in {"hostile", "suspect"}:
            entity_type = "ENEMY_UAV"
        elif domain == "surface" and affiliation in {"hostile", "suspect"}:
            entity_type = "ENEMY_SHIP"
        elif domain == "surface" and affiliation in {"friendly", "assumed_friend"}:
            entity_type = "FRIENDLY_SHIP"
        else:
            entity_type = "UNKNOWN"

        return cls.generate(
            affiliation=affiliation,
            domain=domain,
            entity_type=entity_type,
        )

    @classmethod
    def to_cot_type(cls, sidc: str) -> str:
        """Reverse-map SIDC to a compact CoT type tree string."""

        if not cls.is_valid_sidc(sidc):
            return "g-u-G-U-C"
        affiliation_code = sidc[2]
        symbol_set = sidc[3:5]
        domain = cls._SYMBOL_SET_TO_DOMAIN.get(symbol_set, "land")
        cot_domain = cls._S3M_DOMAIN_TO_COT.get(domain, "g")
        cot_affiliation = cls._S3M_AFFILIATION_TO_COT.get(affiliation_code, "u")
        return f"{cot_domain}-{cot_affiliation}-G-U-C"

    @staticmethod
    def is_valid_sidc(sidc: Optional[str]) -> bool:
        return isinstance(sidc, str) and sidc.isdigit() and len(sidc) == 20

    @classmethod
    def _normalize_affiliation(cls, affiliation: Any) -> str:
        normalized = str(affiliation or "").strip().lower().replace(" ", "_")
        if normalized in cls._AFFILIATION_MAP:
            return normalized
        if normalized in cls._AFFILIATION_ALIASES:
            return cls._AFFILIATION_ALIASES[normalized]
        return "unknown"

    @classmethod
    def _normalize_domain(cls, domain: Any) -> str:
        normalized = str(domain or "").strip().lower()
        if normalized in cls._DOMAIN_TO_SYMBOL_SET:
            return normalized
        if normalized in {"ground", "kinetic"}:
            return "land"
        if normalized in {"sea", "maritime"}:
            return "surface"
        return "land"

    @staticmethod
    def _normalize_entity_key(entity_type: Any) -> str:
        return str(entity_type or "UNKNOWN").strip().upper()

    @classmethod
    def _resolve_dis_affiliation(cls, entity_key: str, force_id: int, country: int) -> str:
        if entity_key.startswith("FRIENDLY_"):
            return "friendly"
        if entity_key.startswith("ENEMY_"):
            return "hostile"
        if entity_key in {"CIVILIAN", "OBSTACLE", "WAYPOINT"}:
            return "neutral"
        if entity_key == "BASE":
            if int(force_id) == 1 or int(country) == 178:
                return "friendly"
        return cls._FORCE_ID_TO_AFFILIATION.get(int(force_id), "unknown")

    @staticmethod
    def _normalize_status(status: Any, planned_flag: Any) -> str:
        if isinstance(planned_flag, bool):
            return "1" if planned_flag else "0"
        if isinstance(status, str) and status.strip().lower() in {"planned", "anticipated", "future"}:
            return "1"
        status_text = str(status).strip()
        if status_text in {"0", "1"}:
            return status_text
        return "0"

    @staticmethod
    def _two_digit(value: Any, default: str) -> str:
        raw = str(value).strip()
        if raw.isdigit():
            return raw.zfill(2)[-2:]
        return default

    @staticmethod
    def _one_digit(value: Any, default: str) -> str:
        raw = str(value).strip()
        if len(raw) == 1 and raw.isdigit():
            return raw
        return default
