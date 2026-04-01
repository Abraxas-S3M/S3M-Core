"""Normalization helpers for Intelligence X deep OSINT records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent


class IntelligenceXNormalizer:
    provider_id = "osint-intelligencex"
    provider_name = "Intelligence X"

    bucket_event_type = {
        "pastes": "data_leak",
        "darknet": "darknet_activity",
        "whois": "infrastructure_change",
        "whois_domain": "infrastructure_change",
        "whois_ip": "infrastructure_change",
        "dumpster": "data_breach",
        "leaks": "data_breach",
        "news": "media_report",
        "web": "web_content",
    }

    bucket_sentiment = {
        "darknet": -0.8,
        "dumpster": -0.8,
        "leaks": -0.8,
        "pastes": -0.6,
        "whois": -0.2,
        "whois_domain": -0.2,
        "whois_ip": -0.2,
        "news": 0.0,
        "web": 0.0,
    }

    bucket_confidence = {
        "darknet": 0.5,
        "dumpster": 0.7,
        "leaks": 0.7,
        "pastes": 0.7,
        "whois": 0.9,
        "whois_domain": 0.9,
        "whois_ip": 0.9,
        "news": 0.6,
        "web": 0.6,
    }

    def _event_type_from_bucket(self, bucket: str) -> str:
        return self.bucket_event_type.get(str(bucket).lower(), "osint_record")

    def _parse_timestamp(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        cleaned = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return datetime.now(timezone.utc)

    def _bucket_key(self, record: dict[str, Any]) -> str:
        bucket = str(record.get("bucket", "")).lower().strip()
        if bucket in {"whois_domain", "whois_ip"}:
            return bucket
        if bucket.startswith("whois"):
            return "whois"
        return bucket

    def _media_label(self, media: Any) -> str:
        mapping = {
            0: "all",
            1: "paste",
            2: "darknet_market",
            3: "whois_domain",
            5: "news",
            24: "document",
        }
        try:
            return mapping.get(int(media), "unknown")
        except (TypeError, ValueError):
            return "unknown"

    def _size_label(self, size: Any) -> str:
        try:
            size_int = int(size)
        except (TypeError, ValueError):
            return "size:unknown"
        if size_int < 50_000:
            return "size:small"
        if size_int < 1_000_000:
            return "size:medium"
        return "size:large"

    def classify_leak_severity(self, record: dict[str, Any]) -> str:
        bucket = self._bucket_key(record)
        size = int(record.get("size", 0) or 0)
        name = str(record.get("name", "")).lower()
        if bucket == "darknet" and size >= 1_000_000:
            return "critical"
        if bucket == "pastes" and any(keyword in name for keyword in ["credential", "password", "passwd", "login", "config"]):
            return "high"
        if bucket in {"whois", "whois_domain", "whois_ip"}:
            return "medium"
        if bucket == "news":
            return "low"
        if bucket in {"dumpster", "leaks"}:
            return "high"
        return "medium"

    def normalize_record(self, record: dict[str, Any]) -> NormalizedGlobalEvent:
        bucket = self._bucket_key(record)
        event_type = self.bucket_event_type.get(bucket, "osint_record")
        sentiment = self.bucket_sentiment.get(bucket, -0.2)
        confidence = self.bucket_confidence.get(bucket, 0.5)
        severity = self.classify_leak_severity(record)
        timestamp = self._parse_timestamp(record.get("date") or record.get("added"))
        return NormalizedGlobalEvent(
            timestamp=timestamp,
            event_type=event_type,
            actors=[],
            country="",
            region="global",
            source_count=1,
            sentiment_score=sentiment,
            language="en",
            tags=[
                "intelx",
                f"bucket:{bucket}",
                f"media:{self._media_label(record.get('media'))}",
                self._size_label(record.get("size")),
                f"date:{timestamp.date().isoformat()}",
                f"severity:{severity}",
            ],
            raw_data_ref=str(record.get("systemid", "")),
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(record.get("storageid", "")) or None,
                confidence=confidence,
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_phonebook(self, selectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for selector in selectors:
            selector_type = str(selector.get("type", "")).lower()
            normalized_type = "email"
            if "domain" in selector_type:
                normalized_type = "domain"
            elif "url" in selector_type:
                normalized_type = "url"
            output.append(
                {
                    "type": normalized_type,
                    "value": str(selector.get("selectorvalue", selector.get("value", ""))),
                    "sources": int(selector.get("sources", selector.get("count", 1)) or 1),
                }
            )
        return output
