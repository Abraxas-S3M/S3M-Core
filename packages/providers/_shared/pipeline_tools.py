"""Simple ingestion pipeline primitives shared by GEOINT pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .utils import compute_observation_hash


class BatchIngestionRunner:
    def run(self, tasks: dict[str, Callable[[], Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, task in tasks.items():
            try:
                out[name] = {"ok": True, "data": task()}
            except Exception as exc:  # pragma: no cover
                out[name] = {"ok": False, "error": str(exc), "data": {"observations": []}}
        return out


class HashBasedDeduplicator:
    def deduplicate(self, observations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        removed = 0
        for obs in observations:
            digest = compute_observation_hash(obs)
            if digest in seen:
                removed += 1
                continue
            seen.add(digest)
            deduped.append(obs)
        return deduped, removed


class ChainedEnrichmentPipeline:
    def __init__(self) -> None:
        self.steps: list[Callable[[dict[str, Any]], dict[str, Any]]] = []

    def add_step(self, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.steps.append(fn)

    def run(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for obs in observations:
            current = obs
            for step in self.steps:
                current = step(current)
            out.append(current)
        return out
