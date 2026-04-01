"""Normalization helpers for GDELT global event feeds."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent


GDELT_COLUMNS = [
    "GLOBALEVENTID",
    "SQLDATE",
    "MonthYear",
    "Year",
    "FractionDate",
    "Actor1Code",
    "Actor1Name",
    "Actor1CountryCode",
    "Actor1KnownGroupCode",
    "Actor1EthnicCode",
    "Actor1Religion1Code",
    "Actor1Religion2Code",
    "Actor1Type1Code",
    "Actor1Type2Code",
    "Actor1Type3Code",
    "Actor2Code",
    "Actor2Name",
    "Actor2CountryCode",
    "Actor2KnownGroupCode",
    "Actor2EthnicCode",
    "Actor2Religion1Code",
    "Actor2Religion2Code",
    "Actor2Type1Code",
    "Actor2Type2Code",
    "Actor2Type3Code",
    "IsRootEvent",
    "EventCode",
    "EventBaseCode",
    "EventRootCode",
    "QuadClass",
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    "Actor1Geo_Type",
    "Actor1Geo_FullName",
    "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code",
    "Actor1Geo_Lat",
    "Actor1Geo_Long",
    "Actor1Geo_FeatureID",
    "Actor2Geo_Type",
    "Actor2Geo_FullName",
    "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code",
    "Actor2Geo_Lat",
    "Actor2Geo_Long",
    "Actor2Geo_FeatureID",
    "ActionGeo_Type",
    "ActionGeo_FullName",
    "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code",
    "ActionGeo_Lat",
    "ActionGeo_Long",
    "ActionGeo_FeatureID",
    "DATEADDED",
    "SOURCEURL",
    "ActionGeo_ADM2Code",
    "ActionGeo_LocationPrecision",
    "SourceCollectionIdentifier",
    "extra_1",
    "extra_2",
    "extra_3",
    "extra_4",
    "extra_5",
]


class GDELTNormalizer:
    provider_id = "osint-gdelt"
    provider_name = "GDELT Project"

    def _parse_timestamp(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        raw = str(value).strip()
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
        cleaned = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return datetime.now(timezone.utc)

    def _as_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _confidence_from_mentions(self, mentions: int) -> float:
        if mentions >= 20:
            return 0.9
        if mentions >= 5:
            return 0.7
        if mentions >= 2:
            return 0.5
        return 0.3

    def _event_type_from_cameo(self, code: str) -> str:
        value = str(code).strip()
        if value.startswith("19"):
            return "conflict"
        if value.startswith("14"):
            return "protest"
        if value.startswith("17"):
            return "coercion"
        if value.startswith("18"):
            return "assault"
        if value.startswith("20"):
            return "mass_violence"
        return "political"

    def severity_from_goldstein(self, goldstein: float) -> str:
        if goldstein < -7:
            return "critical"
        if goldstein < -3:
            return "high"
        if goldstein <= 0:
            return "medium"
        return "low"

    def normalize_article(self, article: dict[str, Any]) -> NormalizedGlobalEvent:
        tone = self._as_float(article.get("tone"), 0.0)
        return NormalizedGlobalEvent(
            timestamp=self._parse_timestamp(article.get("seendate")),
            event_type="media_report",
            actors=[],
            country=str(article.get("sourcecountry", "")).upper(),
            region="global",
            source_count=1,
            sentiment_score=max(-1.0, min(1.0, tone / 100.0)),
            language=str(article.get("language", "en") or "en").lower(),
            tags=[
                "gdelt",
                "article",
                str(article.get("domain", "")),
            ],
            raw_data_ref=str(article.get("url", "")),
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(article.get("url", "")) or None,
                confidence=0.5,
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_cameo_event(self, event: dict[str, Any]) -> NormalizedGlobalEvent:
        code = str(event.get("EventCode", ""))
        mentions = self._as_int(event.get("NumMentions"), 0)
        goldstein = self._as_float(event.get("GoldsteinScale"), 0.0)
        actor1 = str(event.get("Actor1Name", "")).strip()
        actor2 = str(event.get("Actor2Name", "")).strip()
        actors = [name for name in [actor1, actor2] if name]
        lat = event.get("ActionGeo_Lat")
        lon = event.get("ActionGeo_Long")
        point = None
        if lat not in {"", None} and lon not in {"", None}:
            point = GeoPoint(lat=self._as_float(lat), lon=self._as_float(lon))

        severity = self.severity_from_goldstein(goldstein)
        return NormalizedGlobalEvent(
            timestamp=self._parse_timestamp(event.get("SQLDATE")),
            event_type=self._event_type_from_cameo(code),
            actors=actors,
            fatalities=None,
            country=str(event.get("ActionGeo_CountryCode", "")).upper(),
            region="mena",
            source_count=max(self._as_int(event.get("NumSources"), 1), 1),
            sentiment_score=max(-1.0, min(1.0, self._as_float(event.get("AvgTone"), 0.0) / 100.0)),
            goldstein_scale=goldstein,
            language="en",
            geo_point=point,
            tags=["gdelt", f"cameo:{code}", f"severity:{severity}"],
            raw_data_ref=str(event.get("SOURCEURL", "")),
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(event.get("GLOBALEVENTID", "")) or None,
                confidence=self._confidence_from_mentions(mentions),
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_geo_feature(self, feature: dict[str, Any]) -> NormalizedGlobalEvent:
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [0.0, 0.0])
        props = feature.get("properties", {})
        lon = coords[0] if isinstance(coords, list) and len(coords) >= 2 else 0.0
        lat = coords[1] if isinstance(coords, list) and len(coords) >= 2 else 0.0
        tone = self._as_float(props.get("tone"), 0.0)
        code = str(props.get("eventcode", ""))
        return NormalizedGlobalEvent(
            timestamp=self._parse_timestamp(props.get("seendate")),
            event_type=self._event_type_from_cameo(code) if code else "media_report",
            actors=[],
            country=str(props.get("country", props.get("sourcecountry", ""))).upper(),
            region="mena",
            source_count=max(self._as_int(props.get("nummentions"), 1), 1),
            sentiment_score=max(-1.0, min(1.0, tone / 100.0)),
            language=str(props.get("language", "en") or "en").lower(),
            geo_point=GeoPoint(lat=self._as_float(lat), lon=self._as_float(lon)),
            tags=["gdelt", "geo_event", str(props.get("name", "event"))],
            raw_data_ref=str(props.get("url", "")),
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(feature.get("id", "")) or None,
                confidence=0.6,
                classification="UNCLASSIFIED",
            ),
        )

    def parse_cameo_csv(
        self,
        csv_content: str,
        filter_countries: list[str] | None = None,
        filter_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        def map_without_header(row_values: list[str]) -> dict[str, Any]:
            # Tactical context: field exports can shift column positions across mirror datasets.
            compact_map = {
                "GLOBALEVENTID": 0,
                "SQLDATE": 1,
                "Actor1Name": 6,
                "Actor2Name": 19,
                "EventCode": 31,
                "GoldsteinScale": 35,
                "NumMentions": 36,
                "NumSources": 37,
                "AvgTone": 39,
                "ActionGeo_CountryCode": 56,
                "ActionGeo_Lat": 58,
                "ActionGeo_Long": 59,
                "SOURCEURL": 62,
            }
            standard_map = {
                "GLOBALEVENTID": 0,
                "SQLDATE": 1,
                "Actor1Name": 6,
                "Actor2Name": 16,
                "EventCode": 26,
                "GoldsteinScale": 30,
                "NumMentions": 31,
                "NumSources": 32,
                "AvgTone": 34,
                "ActionGeo_CountryCode": 50,
                "ActionGeo_Lat": 52,
                "ActionGeo_Long": 53,
                "SOURCEURL": 57,
            }
            use_compact = len(row_values) >= 63 and (not row_values[26].strip()) and row_values[31].strip().isdigit()
            index_map = compact_map if use_compact else standard_map
            mapped = {key: (row_values[idx] if idx < len(row_values) else "") for key, idx in index_map.items()}
            for idx, value in enumerate(row_values):
                mapped[f"col_{idx}"] = value
            return mapped

        countries = {c.upper() for c in (filter_countries or [])}
        code_prefixes = [str(code) for code in (filter_codes or [])]
        raw_csv = csv_content.strip()
        if "\t" not in raw_csv and "\\t" in raw_csv:
            raw_csv = raw_csv.replace("\\t", "\t")
        stream = io.StringIO(raw_csv)
        reader = csv.reader(stream, delimiter="\t")
        rows = list(reader)
        if not rows:
            return []

        first = rows[0]
        has_header = "EventCode" in first and "ActionGeo_CountryCode" in first
        header = first if has_header else list(GDELT_COLUMNS)
        data_rows = rows[1:] if has_header else rows

        parsed: list[dict[str, Any]] = []
        for row in data_rows:
            if not row:
                continue
            if has_header:
                if len(row) < len(header):
                    row = row + [""] * (len(header) - len(row))
                record = dict(zip(header, row))
            else:
                record = map_without_header(row)
            country = str(record.get("ActionGeo_CountryCode", "")).upper()
            code = str(record.get("EventCode", ""))
            if countries and country not in countries:
                continue
            if code_prefixes and not any(code.startswith(prefix) for prefix in code_prefixes):
                continue
            parsed.append(record)
        return parsed
