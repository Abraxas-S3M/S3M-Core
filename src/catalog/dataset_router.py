"""Dataset routing logic for scenario-aligned training packet assembly.

Military/tactical context:
Routing decisions prioritize datasets with the strongest domain overlap so
scenario packets are grounded in relevant operational evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .dataset_catalog import DatasetRecord


@dataclass(frozen=True)
class DatasetRoute:
    """One ranked route candidate returned by DatasetRouter."""

    dataset_id: str
    score: int
    matched_scenario_domains: tuple[str, ...]
    reasons: tuple[str, ...]
    record: DatasetRecord


class DatasetRouter:
    """Rank dataset catalog entries by track and scenario-domain fit."""

    def __init__(self, records: Sequence[DatasetRecord]) -> None:
        self._records = tuple(records)

    def route(
        self,
        *,
        training_track: str,
        scenario_domains: Sequence[str],
        top_k: int = 8,
        requested_packet_types: Sequence[str] | None = None,
    ) -> tuple[DatasetRoute, ...]:
        """Return ranked datasets matching the specified route intent."""
        normalized_track = _norm(training_track)
        normalized_domains = tuple(dict.fromkeys(_norm(item) for item in scenario_domains if str(item).strip()))
        normalized_packet_types = (
            tuple(dict.fromkeys(_norm(item) for item in requested_packet_types if str(item).strip()))
            if requested_packet_types
            else ()
        )

        routed: list[DatasetRoute] = []
        for record in self._records:
            if not record.enabled:
                continue
            if not _track_matches(record, normalized_track):
                continue
            if normalized_packet_types and not set(normalized_packet_types).intersection(record.supported_packet_types):
                continue
            route = self._score_record(
                record=record,
                training_track=normalized_track,
                scenario_domains=normalized_domains,
            )
            if route is not None:
                routed.append(route)

        routed.sort(key=lambda item: item.score, reverse=True)
        if top_k < 1:
            return tuple()
        return tuple(routed[:top_k])

    def _score_record(
        self,
        *,
        record: DatasetRecord,
        training_track: str,
        scenario_domains: tuple[str, ...],
    ) -> DatasetRoute | None:
        matched_domains = tuple(sorted(set(record.supported_scenario_domains).intersection(scenario_domains)))
        if scenario_domains and not matched_domains:
            return None

        reasons: list[str] = []
        score = record.routing_priority * 10
        reasons.append(f"base_priority={record.routing_priority}")

        if training_track in record.supported_training_tracks:
            score += 40
            reasons.append("exact_track")
        elif "shared" in record.supported_training_tracks:
            score += 10
            reasons.append("shared_track")

        score += len(matched_domains) * 30
        if matched_domains:
            reasons.append(f"domain_overlap={len(matched_domains)}")

        # Tactical routing boosts for key Saudi MOD packet intents.
        if "bilingual" in scenario_domains and _is_bilingual_capable(record):
            score += 30
            reasons.append("bilingual_capable")

        if ("cop_intel" in scenario_domains or "isr_collection" in scenario_domains) and _is_cop_geospatial_capable(record):
            score += 25
            reasons.append("cop_geospatial_capable")

        if "cyber_electronic_warfare" in scenario_domains and _is_cyber_capable(record):
            score += 25
            reasons.append("cyber_capable")

        if "logistics_sustainment" in scenario_domains and _is_logistics_capable(record):
            score += 20
            reasons.append("logistics_capable")

        return DatasetRoute(
            dataset_id=record.dataset_id,
            score=score,
            matched_scenario_domains=matched_domains,
            reasons=tuple(reasons),
            record=record,
        )


def _norm(value: str) -> str:
    return str(value).strip().lower()


def _track_matches(record: DatasetRecord, training_track: str) -> bool:
    tracks = set(record.supported_training_tracks)
    return training_track in tracks or "shared" in tracks


def _is_bilingual_capable(record: DatasetRecord) -> bool:
    language = record.language.lower()
    if "bilingual" in language:
        return True
    return "arabic" in language and "english" in language


def _is_cop_geospatial_capable(record: DatasetRecord) -> bool:
    domains = set(record.operational_domains)
    return bool(domains.intersection({"cop", "geospatial", "isr", "intelligence", "maritime"}))


def _is_cyber_capable(record: DatasetRecord) -> bool:
    domains = set(record.operational_domains)
    return bool(domains.intersection({"cyber", "electronic_warfare", "threat_intelligence"}))


def _is_logistics_capable(record: DatasetRecord) -> bool:
    domains = set(record.operational_domains)
    return bool(domains.intersection({"logistics", "sustainment", "supply_chain"}))
