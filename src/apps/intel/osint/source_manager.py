"""Source registration and cataloging for air-gapped OSINT ingestion."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import yaml

from src.apps.intel.models import IntelSource, SourceReliability, SourceType


class SourceManager:
    """Manage intelligence source metadata and reliability grading."""

    def __init__(self, sources_config: str = "configs/intel/sources.yaml") -> None:
        self.sources_config = sources_config
        self._sources: dict[str, IntelSource] = {}
        self.load_sources()

    def _save_sources(self) -> None:
        os.makedirs(os.path.dirname(self.sources_config), exist_ok=True)
        payload = {"sources": [source.to_dict() for source in self._sources.values()]}
        with open(self.sources_config, "w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)

    @staticmethod
    def _as_source_type(value: SourceType | str) -> SourceType:
        if isinstance(value, SourceType):
            return value
        return SourceType[str(value).strip()]

    @staticmethod
    def _as_reliability(value: SourceReliability | str) -> SourceReliability:
        if isinstance(value, SourceReliability):
            return value
        return SourceReliability[str(value).strip()]

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def load_sources(self) -> list[IntelSource]:
        """Load source registry from YAML config."""
        self._sources = {}
        if not os.path.exists(self.sources_config):
            return []
        with open(self.sources_config, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        for row in raw.get("sources", []):
            try:
                source = IntelSource(
                    source_id=str(row["source_id"]),
                    name=str(row["name"]),
                    source_type=self._as_source_type(row["source_type"]),
                    reliability=self._as_reliability(row["reliability"]),
                    regions_covered=list(row.get("regions_covered", [])),
                    topics_covered=list(row.get("topics_covered", [])),
                    language=str(row.get("language", "en")),
                    update_frequency=str(row.get("update_frequency", "manual")),
                    last_ingestion=self._parse_dt(row.get("last_ingestion")),
                    items_ingested=int(row.get("items_ingested", 0)),
                    data_path=row.get("data_path"),
                    active=bool(row.get("active", True)),
                )
                self._sources[source.source_id] = source
            except Exception:
                continue
        return list(self._sources.values())

    def register_source(
        self,
        name: str,
        source_type: SourceType | str,
        reliability: SourceReliability | str,
        regions: list[str],
        topics: list[str],
        language: str,
        frequency: str,
        data_path: str | None = None,
    ) -> IntelSource:
        source = IntelSource(
            source_id=f"src-{uuid4().hex[:10]}",
            name=name,
            source_type=self._as_source_type(source_type),
            reliability=self._as_reliability(reliability),
            regions_covered=list(regions),
            topics_covered=list(topics),
            language=language,
            update_frequency=frequency,
            data_path=data_path,
        )
        self._sources[source.source_id] = source
        self._save_sources()
        return source

    def get_source(self, source_id: str) -> IntelSource | None:
        return self._sources.get(source_id)

    def get_sources(
        self,
        source_type: SourceType | str | None = None,
        region: str | None = None,
        active_only: bool = True,
    ) -> list[IntelSource]:
        values = list(self._sources.values())
        if active_only:
            values = [src for src in values if src.active]
        if source_type is not None:
            wanted = self._as_source_type(source_type)
            values = [src for src in values if src.source_type == wanted]
        if region:
            needle = region.strip().lower()
            values = [
                src
                for src in values
                if any(needle in candidate.lower() for candidate in src.regions_covered)
            ]
        return values

    def update_source(self, source_id: str, **kwargs) -> IntelSource:
        source = self._sources[source_id]
        patch = dict(kwargs)
        if "source_type" in patch:
            patch["source_type"] = self._as_source_type(patch["source_type"])
        if "reliability" in patch:
            patch["reliability"] = self._as_reliability(patch["reliability"])
        updated = replace(source, **patch)
        self._sources[source_id] = updated
        self._save_sources()
        return updated

    def deactivate_source(self, source_id: str) -> None:
        self.update_source(source_id, active=False)

    def get_source_stats(self) -> dict:
        by_type = Counter(src.source_type.value for src in self._sources.values())
        by_rel = Counter(src.reliability.value for src in self._sources.values())
        by_region = Counter()
        for src in self._sources.values():
            for region in src.regions_covered:
                by_region[region] += 1
        return {
            "total": len(self._sources),
            "by_type": dict(by_type),
            "by_reliability": dict(by_rel),
            "by_region": dict(by_region),
        }

    def create_default_sources(self) -> list[IntelSource]:
        """Create Saudi-focused baseline source set for sovereign operations."""
        defaults = [
            ("Gulf News Feed", SourceType.NEWS_FEED, SourceReliability.B_USUALLY_RELIABLE, ["Persian Gulf", "Arabian Peninsula"], ["diplomacy", "energy_security"], "en", "daily"),
            ("Arabic Media Monitor", SourceType.NEWS_FEED, SourceReliability.B_USUALLY_RELIABLE, ["Arabian Peninsula", "Levant"], ["regional_stability", "proxy_warfare"], "ar", "daily"),
            ("Red Sea Maritime Intel", SourceType.MARITIME_AIS, SourceReliability.A_RELIABLE, ["Red Sea", "Bab el-Mandeb"], ["maritime_security"], "en", "realtime"),
            ("Yemen Conflict Tracker", SourceType.OSINT_TOOL, SourceReliability.C_FAIRLY_RELIABLE, ["Yemen", "Gulf of Aden"], ["drone_threats", "terrorism"], "both", "daily"),
            ("Cyber Threat Intel Feed", SourceType.CYBER_CTI, SourceReliability.B_USUALLY_RELIABLE, ["Global"], ["cyber_operations"], "en", "hourly"),
            ("Satellite Imagery Analysis", SourceType.SATELLITE, SourceReliability.A_RELIABLE, ["Persian Gulf", "Red Sea"], ["maritime_security", "border_security"], "en", "daily"),
            ("Gulf Diplomatic Wire", SourceType.GOVERNMENT_REPORT, SourceReliability.A_RELIABLE, ["GCC"], ["diplomacy"], "both", "weekly"),
            ("Horn of Africa Monitor", SourceType.NEWS_FEED, SourceReliability.C_FAIRLY_RELIABLE, ["Horn of Africa"], ["regional_stability", "maritime_security"], "en", "daily"),
            ("Strait of Hormuz Watch", SourceType.MARITIME_AIS, SourceReliability.A_RELIABLE, ["Strait of Hormuz"], ["maritime_security", "energy_security"], "en", "realtime"),
            ("Iran Regional Activity", SourceType.OSINT_TOOL, SourceReliability.C_FAIRLY_RELIABLE, ["Iran", "Levant"], ["proxy_warfare", "weapons_proliferation"], "en", "daily"),
            ("Social Media OSINT", SourceType.SOCIAL_MEDIA, SourceReliability.D_NOT_USUALLY_RELIABLE, ["Global"], ["disinformation", "terrorism"], "both", "hourly"),
            ("Academic Threat Research", SourceType.ACADEMIC, SourceReliability.B_USUALLY_RELIABLE, ["Global"], ["cyber_operations", "weapons_proliferation"], "en", "weekly"),
        ]
        existing_names = {s.name for s in self._sources.values()}
        created: list[IntelSource] = []
        for row in defaults:
            if row[0] in existing_names:
                continue
            created.append(
                self.register_source(
                    name=row[0],
                    source_type=row[1],
                    reliability=row[2],
                    regions=row[3],
                    topics=row[4],
                    language=row[5],
                    frequency=row[6],
                )
            )
        return created
