"""Normalization helpers for Media Cloud narrative monitoring feeds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent


class MediaCloudNormalizer:
    provider_id = "osint-mediacloud"
    provider_name = "Media Cloud"

    def _parse_timestamp(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        raw = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return datetime.now(timezone.utc)

    def _word_count_range(self, word_count: int) -> str:
        if word_count < 300:
            return "short"
        if word_count < 800:
            return "medium"
        return "long"

    def normalize_story(self, story: dict[str, Any]) -> NormalizedGlobalEvent:
        word_count = int(story.get("word_count", 0) or 0)
        language = str(story.get("language", "en") or "en").lower()
        return NormalizedGlobalEvent(
            timestamp=self._parse_timestamp(story.get("publish_date")),
            event_type="media_report",
            actors=[],
            country="",
            region="global",
            source_count=1,
            sentiment_score=0.0,
            language=language,
            tags=[
                "mediacloud",
                str(story.get("media_name", "")),
                language,
                f"word_count_{self._word_count_range(word_count)}",
            ],
            raw_data_ref=str(story.get("url", "")),
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(story.get("stories_id", "")) or None,
                confidence=0.4,
                classification="UNCLASSIFIED",
            ),
        )

    def detect_narrative_surge(
        self,
        counts: list[dict[str, Any]],
        threshold_multiplier: float = 3.0,
        query: str = "",
    ) -> list[dict[str, Any]]:
        sorted_counts = sorted(counts, key=lambda item: str(item.get("date", "")))
        surges: list[dict[str, Any]] = []
        for idx, item in enumerate(sorted_counts):
            if idx < 7:
                continue
            prior = sorted_counts[max(0, idx - 7):idx]
            average = sum(float(p.get("count", 0) or 0) for p in prior) / max(len(prior), 1)
            current = float(item.get("count", 0) or 0)
            if average <= 0:
                continue
            multiplier = current / average
            if multiplier > threshold_multiplier:
                surges.append(
                    {
                        "date": item.get("date"),
                        "count": int(current),
                        "average": round(average, 3),
                        "multiplier": round(multiplier, 3),
                        "query": query,
                    }
                )
        return surges

    def normalize_trend(self, counts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sorted_counts = sorted(counts, key=lambda item: str(item.get("date", "")))
        surges = {item["date"] for item in self.detect_narrative_surge(sorted_counts)}
        normalized: list[dict[str, Any]] = []
        prev = None
        for item in sorted_counts:
            count = int(item.get("count", 0) or 0)
            if prev in {None, 0}:
                change_pct = 0.0
            else:
                change_pct = ((count - prev) / prev) * 100.0
            normalized.append(
                {
                    "date": item.get("date"),
                    "count": count,
                    "change_pct": round(change_pct, 3),
                    "surge": str(item.get("date")) in surges,
                }
            )
            prev = count
        return normalized
