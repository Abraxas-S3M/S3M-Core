"""OSINT fusion pipeline for global events, media, and deep OSINT feeds."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from packages.providers._shared import BatchIngestionRunner, HashBasedDeduplicator, ensure_directory
from packages.providers.osint_acled.adapter import ACLEDAdapter
from packages.providers.osint_gdelt.adapter import GDELTAdapter
from packages.providers.osint_intelligencex.adapter import IntelligenceXAdapter
from packages.providers.osint_mediacloud.adapter import MediaCloudAdapter
from packages.schemas.event_intel.models import NormalizedGlobalEvent


class CrossProviderEntityResolver:
    """Resolve likely duplicate event reports across OSINT providers."""

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))

    def _country_alias(self, value: str) -> str:
        text = str(value).strip().upper()
        aliases = {
            "YEMEN": "YE",
            "SAUDI ARABIA": "SA",
            "IRAN": "IR",
            "IRAQ": "IQ",
            "SYRIA": "SY",
            "JORDAN": "JO",
            "EGYPT": "EG",
            "SUDAN": "SD",
            "ERITREA": "ER",
            "DJIBOUTI": "DJ",
            "SOMALIA": "SO",
            "OMAN": "OM",
            "QATAR": "QA",
            "KUWAIT": "KW",
            "BAHRAIN": "BH",
            "UNITED ARAB EMIRATES": "AE",
        }
        return aliases.get(text, text)

    def is_match(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_date = str(left.get("timestamp", ""))[:10]
        right_date = str(right.get("timestamp", ""))[:10]
        if not left_date or left_date != right_date:
            return False
        left_country = self._country_alias(str(left.get("country", "")))
        right_country = self._country_alias(str(right.get("country", "")))
        if left_country != right_country:
            return False
        lgeo = left.get("geo_point") or {}
        rgeo = right.get("geo_point") or {}
        if not all(key in lgeo for key in ("lat", "lon")) or not all(key in rgeo for key in ("lat", "lon")):
            return False
        distance = self.haversine_km(float(lgeo["lat"]), float(lgeo["lon"]), float(rgeo["lat"]), float(rgeo["lon"]))
        return distance < 50.0


class OSINTFusionPipeline:
    def __init__(self) -> None:
        self.providers = {
            "osint-gdelt": GDELTAdapter(mode="airgapped"),
            "osint-acled": ACLEDAdapter(mode="airgapped"),
            "osint-mediacloud": MediaCloudAdapter(mode="airgapped"),
            "osint-intelligencex": IntelligenceXAdapter(mode="airgapped"),
        }
        self.batch_runner = BatchIngestionRunner()
        self.deduplicator = HashBasedDeduplicator()
        self.entity_resolver = CrossProviderEntityResolver()
        self._last_events: list[dict[str, Any]] = []

    @staticmethod
    def _country_to_iso(value: str) -> str:
        text = str(value).strip().upper()
        aliases = {
            "YEMEN": "YE",
            "SAUDI ARABIA": "SA",
            "IRAN": "IR",
            "IRAQ": "IQ",
            "SYRIA": "SY",
            "JORDAN": "JO",
            "EGYPT": "EG",
            "SUDAN": "SD",
            "ERITREA": "ER",
            "DJIBOUTI": "DJ",
            "SOMALIA": "SO",
            "OMAN": "OM",
            "QATAR": "QA",
            "KUWAIT": "KW",
            "BAHRAIN": "BH",
            "UNITED ARAB EMIRATES": "AE",
        }
        return aliases.get(text, text)

    def _normalize_country_codes(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for event in events:
            item = dict(event)
            item["country"] = self._country_to_iso(str(item.get("country", "")))
            normalized.append(item)
        return normalized

    def _country_code(self, value: str) -> str:
        text = str(value).strip().upper()
        aliases = {
            "YEMEN": "YE",
            "SAUDI ARABIA": "SA",
            "IRAN": "IR",
            "IRAQ": "IQ",
            "SYRIA": "SY",
            "JORDAN": "JO",
            "EGYPT": "EG",
            "SUDAN": "SD",
            "ERITREA": "ER",
            "DJIBOUTI": "DJ",
            "SOMALIA": "SO",
            "OMAN": "OM",
            "QATAR": "QA",
            "KUWAIT": "KW",
            "BAHRAIN": "BH",
            "UNITED ARAB EMIRATES": "AE",
        }
        return aliases.get(text, text)

    def _to_dict(self, event: Any) -> dict[str, Any]:
        if isinstance(event, dict):
            payload = dict(event)
        elif is_dataclass(event):
            payload = asdict(event)
        else:
            payload = dict(event)
        if isinstance(payload.get("timestamp"), datetime):
            payload["timestamp"] = payload["timestamp"].isoformat()
        if "provider_id" not in payload and isinstance(payload.get("provenance"), dict):
            payload["provider_id"] = payload["provenance"].get("provider_id")
        if "country" in payload:
            payload["country"] = self._country_code(str(payload.get("country", "")))
        return payload

    def _normalize_output(self, items: list[Any]) -> list[dict[str, Any]]:
        return [self._to_dict(item) for item in items]

    def _store_merged(self, payload: dict[str, Any]) -> str:
        out_dir = ensure_directory("data/integrations/osint-merged/")
        out_file = out_dir / f"osint_merged_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        out_file.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return str(out_file)

    def _merge_gdelt_acled(self, gdelt_events: list[dict[str, Any]], acled_events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        merged: list[dict[str, Any]] = []
        used_gdelt: set[int] = set()
        deduped = 0
        for acled in acled_events:
            match_idx = -1
            for idx, gdelt in enumerate(gdelt_events):
                if idx in used_gdelt:
                    continue
                if self.entity_resolver.is_match(acled, gdelt):
                    match_idx = idx
                    break
            if match_idx >= 0:
                gdelt = gdelt_events[match_idx]
                used_gdelt.add(match_idx)
                deduped += 1
                combined = dict(acled)
                combined["provider_id"] = "merged-acled-gdelt"
                combined["source_count"] = max(int(acled.get("source_count", 1)), int(gdelt.get("source_count", 1)))
                combined["sentiment_score"] = float(gdelt.get("sentiment_score", acled.get("sentiment_score", 0.0)))
                combined["metadata"] = dict(combined.get("metadata", {}))
                combined["metadata"]["gdelt_media_mentions"] = int(gdelt.get("source_count", 1))
                combined["metadata"]["gdelt_tone"] = float(gdelt.get("sentiment_score", 0.0))
                tags = set(acled.get("tags", [])) | set(gdelt.get("tags", [])) | {"merged:gdelt+acled"}
                combined["tags"] = sorted(tags)
                merged.append(combined)
            else:
                merged.append(acled)

        for idx, gdelt in enumerate(gdelt_events):
            if idx not in used_gdelt:
                merged.append(gdelt)
        return merged, deduped

    def ingest_all(self, days_back: int = 1) -> dict[str, Any]:
        tasks = {
            "gdelt-cameo": lambda: self.providers["osint-gdelt"].fetch_cameo_events(
                country_codes=self.providers["osint-gdelt"].config.mena_country_codes
            ),
            "gdelt-articles": lambda: self.providers["osint-gdelt"].fetch_articles("saudi OR yemen OR iran", timespan=f"{max(days_back, 1)}d"),
            "acled": lambda: self.providers["osint-acled"].fetch_saudi_region(days_back=days_back),
            "mediacloud-stories": lambda: self.providers["osint-mediacloud"].fetch_stories("gulf security", days_back=max(days_back, 7), limit=100),
            "intelx": lambda: self.providers["osint-intelligencex"].search("aramco.com", max_results=50),
        }
        raw = self.batch_runner.run(tasks)

        gdelt_conflict = self._normalize_output(self.providers["osint-gdelt"].normalize(raw["gdelt-cameo"]["data"]))
        gdelt_articles = self._normalize_output(self.providers["osint-gdelt"].normalize(raw["gdelt-articles"]["data"]))
        acled_events = self._normalize_output(self.providers["osint-acled"].normalize(raw["acled"]["data"]))
        mediacloud_events = self._normalize_output(self.providers["osint-mediacloud"].normalize(raw["mediacloud-stories"]["data"]))
        intelx_events = self._normalize_output(self.providers["osint-intelligencex"].normalize(raw["intelx"]["data"]))

        merged_conflict, deduped = self._merge_gdelt_acled(gdelt_conflict, acled_events)
        merged_conflict, hash_removed = self.deduplicator.deduplicate(merged_conflict)
        merged_all = list(merged_conflict) + gdelt_articles + mediacloud_events + intelx_events

        by_provider = {
            "osint-gdelt": len(gdelt_conflict) + len(gdelt_articles),
            "osint-acled": len(acled_events),
            "osint-mediacloud": len(mediacloud_events),
            "osint-intelligencex": len(intelx_events),
        }
        by_region: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)
        for event in merged_all:
            by_region[str(event.get("region", "unknown"))] += 1
            severity = "medium"
            for tag in event.get("tags", []):
                if str(tag).startswith("severity:"):
                    severity = str(tag).split(":", 1)[1]
                    break
            by_severity[severity] += 1

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": merged_all,
            "summary": {
                "total_events": len(merged_all),
                "by_provider": by_provider,
                "by_region": dict(by_region),
                "by_severity": dict(by_severity),
                "deduplicated": deduped + hash_removed,
            },
        }
        self._store_merged(payload)
        self._last_events = merged_all
        return payload["summary"]

    def ingest_conflict_events(self, region: str = "all", days_back: int = 7) -> dict[str, Any]:
        gdelt = self.providers["osint-gdelt"].fetch_cameo_events(country_codes=self.providers["osint-gdelt"].config.mena_country_codes)
        acled = self.providers["osint-acled"].fetch_events(
            countries=self.providers["osint-acled"].config.saudi_relevant_countries,
            event_types=["Battles", "Explosions/Remote violence"],
            date_from=(datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat(),
            date_to=datetime.now(timezone.utc).date().isoformat(),
            limit=500,
        )
        gdelt_norm = [self._to_dict(item) for item in self.providers["osint-gdelt"].normalize(gdelt) if self._to_dict(item).get("event_type") == "conflict"]
        acled_norm = [self._to_dict(item) for item in self.providers["osint-acled"].normalize(acled) if self._to_dict(item).get("event_type") in {"conflict", "explosion"}]
        gdelt_norm = self._normalize_country_codes(gdelt_norm)
        acled_norm = self._normalize_country_codes(acled_norm)
        merged, deduped = self._merge_gdelt_acled(gdelt_norm, acled_norm)
        if region != "all":
            merged = [item for item in merged if region.lower() in str(item.get("region", "")).lower()]
        self._last_events = merged
        return {"count": len(merged), "events": merged, "region": region, "deduplicated": deduped}

    def ingest_media_landscape(self, query: str, days_back: int = 30) -> dict[str, Any]:
        gdelt_articles = self.providers["osint-gdelt"].fetch_articles(query=query, timespan=f"{days_back}d", max_records=50)
        mc_trend = self.providers["osint-mediacloud"].fetch_story_count_timeseries(query=query, days_back=days_back, period="day")
        mc_compare = self.providers["osint-mediacloud"].compare_arabic_english(query=query, days_back=max(7, days_back // 2))
        mc_words = self.providers["osint-mediacloud"].fetch_word_frequency(query=query)
        trend = self.providers["osint-mediacloud"].normalizer.normalize_trend(mc_trend.get("counts", []))
        surges = self.providers["osint-mediacloud"].normalizer.detect_narrative_surge(mc_trend.get("counts", []), query=query)
        return {
            "total_articles": len(gdelt_articles.get("articles", [])),
            "daily_trend": trend,
            "surges": surges,
            "arabic_english_ratio": mc_compare.get("coverage_ratio", 1.0),
            "top_words": mc_words.get("word_counts", []),
        }

    def ingest_dark_osint(self, days_back: int = 7) -> dict[str, Any]:
        del days_back
        intel = self.providers["osint-intelligencex"].search_saudi_infrastructure()
        critical_findings: list[dict[str, Any]] = []
        leaks_found = 0
        darknet_mentions = 0
        for term in self.providers["osint-intelligencex"].config.saudi_search_terms:
            results = self.providers["osint-intelligencex"].search(term=term, max_results=50)
            for record in results.get("records", []):
                severity = self.providers["osint-intelligencex"].normalizer.classify_leak_severity(record)
                bucket = str(record.get("bucket", "")).lower()
                if bucket in {"pastes", "dumpster", "leaks"}:
                    leaks_found += 1
                if bucket == "darknet":
                    darknet_mentions += 1
                if severity == "critical":
                    critical_findings.append({"term": term, "record": record, "severity": severity})
        return {
            "leaks_found": leaks_found,
            "darknet_mentions": darknet_mentions,
            "by_term": intel.get("terms", {}),
            "critical_findings": critical_findings,
        }

    def feed_to_early_warning(self, events: list[NormalizedGlobalEvent] | list[dict[str, Any]]) -> dict[str, Any]:
        indicators = {
            "Yemen Escalation": 0,
            "Maritime Piracy Index": 0,
            "Hormuz Tension": 0,
            "Drone/UAV Threat Level": 0,
            "GCC Cyber Threat": 0,
        }
        critical = 0
        for event in events:
            item = self._to_dict(event)
            country = str(item.get("country", "")).upper()
            event_type = str(item.get("event_type", "")).lower()
            text = " ".join(str(t).lower() for t in item.get("tags", []))
            if country == "YE" and item.get("fatalities"):
                indicators["Yemen Escalation"] += int(item.get("fatalities", 0))
            if "red sea" in text:
                indicators["Maritime Piracy Index"] += 1
            if country == "IR" and event_type in {"conflict", "coercion", "assault"}:
                indicators["Hormuz Tension"] += 1
            if "drone" in text or "uav" in text:
                indicators["Drone/UAV Threat Level"] += 1
            if event_type in {"data_leak", "data_breach", "darknet_activity"}:
                indicators["GCC Cyber Threat"] += 1
            if any(str(t).endswith("critical") for t in item.get("tags", [])):
                critical += 1
        indicators["crisis_triggered"] = critical >= 3
        return indicators

    def feed_to_briefing_generator(self, events: list[NormalizedGlobalEvent] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for event in events:
            item = self._to_dict(event)
            items.append(
                {
                    "source": "OSINT",
                    "type": "osint",
                    "headline": f"{item.get('event_type', 'event')} in {item.get('country', 'unknown')}",
                    "summary": {
                        "actors": item.get("actors", []),
                        "fatalities": item.get("fatalities"),
                        "sentiment": item.get("sentiment_score", 0.0),
                        "source_count": item.get("source_count", 0),
                    },
                    "timestamp": item.get("timestamp"),
                }
            )
        return items

    def get_regional_summary(self) -> dict[str, Any]:
        regions = {
            "Arabian Peninsula": ["SA", "AE", "OM", "QA", "BH", "KW"],
            "Yemen": ["YE"],
            "Persian Gulf": ["IR", "IQ", "KW", "BH", "QA", "AE", "SA"],
            "Red Sea": ["YE", "ER", "DJ", "EG", "SD", "SA"],
            "Iran": ["IR"],
            "Levant": ["SY", "JO", "IQ"],
            "Horn of Africa": ["SO", "DJ", "ER", "SD"],
            "North Africa": ["EG", "SD"],
        }
        summary: dict[str, Any] = {}
        for name, country_codes in regions.items():
            region_events = [event for event in self._last_events if str(event.get("country", "")).upper() in country_codes]
            severities: dict[str, int] = defaultdict(int)
            actors: dict[str, int] = defaultdict(int)
            for event in region_events:
                severity = "medium"
                for tag in event.get("tags", []):
                    if str(tag).startswith("severity:"):
                        severity = str(tag).split(":", 1)[1]
                        break
                severities[severity] += 1
                for actor in event.get("actors", []):
                    actors[str(actor)] += 1
            summary[name] = {
                "event_count": len(region_events),
                "severity_distribution": dict(severities),
                "trend_direction": "rising" if any(v > 5 for v in severities.values()) else "stable",
                "top_actors": sorted(actors.items(), key=lambda kv: kv[1], reverse=True)[:5],
            }
        return {"regions": summary}

    def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "providers": {provider_id: adapter.health_check() for provider_id, adapter in self.providers.items()}}
