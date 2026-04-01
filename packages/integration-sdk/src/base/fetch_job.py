"""Fetch job runner for scheduled or on-demand provider ingestion."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .provider_adapter import ProviderAdapter


@dataclass
class FetchJobConfig:
    """Fetch job configuration for tactical ingestion workflows."""

    provider_id: str
    interval_seconds: float = 300.0
    params: Dict[str, Any] = field(default_factory=dict)
    max_runs: Optional[int] = None


class FetchJobRunner:
    """Runs repeated fetch+normalize cycles and captures run history."""

    def __init__(self, adapter: ProviderAdapter, config: FetchJobConfig):
        self.adapter = adapter
        self.config = config
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.run_history: List[Dict[str, Any]] = []

    def run_once(self) -> List[Any]:
        started_at = datetime.now(timezone.utc)
        records = self.adapter.fetch_and_normalize(self.config.params)
        self.run_history.append(
            {
                "provider_id": self.config.provider_id,
                "started_at": started_at.isoformat(),
                "record_count": len(records),
            }
        )
        return records

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        def _run() -> None:
            runs = 0
            while not self._stop_event.is_set():
                self.run_once()
                runs += 1
                if self.config.max_runs is not None and runs >= self.config.max_runs:
                    break
                self._stop_event.wait(max(self.config.interval_seconds, 0.01))

        self._thread = threading.Thread(target=_run, daemon=True, name=f"fetch-job-{self.config.provider_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
