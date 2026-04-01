"""Air-gapped OSINT ingestion from dropped JSON/CSV/TXT files."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.apps._shared import clamp
from src.apps.intel.models import OSINTItem, SourceReliability
from src.apps.intel.osint.analyzer import OSINTAnalyzer
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import QueryRequest


class OSINTIngester:
    """Ingest file-based OSINT records for offline tactical intelligence workflows."""

    def __init__(self, watch_dir: str = "data/intel/incoming/") -> None:
        self.watch_dir = watch_dir
        self._processed_files: set[str] = set()
        self._items: list[OSINTItem] = []
        self._errors: list[str] = []
        self._source_reliability: dict[str, SourceReliability] = {}
        os.makedirs(self.watch_dir, exist_ok=True)
        self.analyzer = OSINTAnalyzer()

    def set_source_reliability(self, source_id: str, reliability: SourceReliability) -> None:
        self._source_reliability[source_id] = reliability

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return datetime.now(timezone.utc)

    def _item_from_record(self, record: dict, source_id: str) -> OSINTItem:
        region = record.get("region") or record.get("regions") or "Global"
        topic = record.get("topic") or record.get("topics") or "regional_stability"
        regions = region if isinstance(region, list) else [str(region)]
        topics = topic if isinstance(topic, list) else [str(topic)]
        item = OSINTItem(
            item_id=f"osint-{uuid4().hex[:12]}",
            source_id=source_id,
            timestamp=self._parse_timestamp(record.get("timestamp")),
            title=str(record.get("title", "Untitled OSINT Item")),
            content=str(record.get("content", "")),
            language=str(record.get("language", "auto")),
            url=record.get("url"),
            regions=regions,
            topics=topics,
            entities=[],
        )
        return self.analyzer.analyze(item)

    def ingest_file(self, filepath: str, source_id: str) -> list[OSINTItem]:
        """
        Ingest a single dropped file.

        Supported formats:
        - JSON list of records
        - CSV with title/content/timestamp/url/region/topic
        - TXT line/paragraph entries
        """
        path = Path(filepath)
        if not path.is_absolute():
            # Allow caller-provided relative paths that already point to a real file.
            if path.exists():
                path = path.resolve()
            else:
                path = (Path(self.watch_dir) / path).resolve()
        records: list[dict] = []

        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                records = [row for row in payload if isinstance(row, dict)]
            elif isinstance(payload, dict):
                records = [payload]
        elif path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    records.append(dict(row))
        elif path.suffix.lower() == ".txt":
            text = path.read_text(encoding="utf-8")
            chunks = [chunk.strip() for chunk in text.splitlines() if chunk.strip()]
            if len(chunks) <= 1:
                chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
            for idx, chunk in enumerate(chunks, start=1):
                records.append(
                    {
                        "title": f"Text Intel Item {idx}",
                        "content": chunk,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "url": None,
                        "region": "Global",
                        "topic": "regional_stability",
                    }
                )
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        items = [self._item_from_record(record, source_id=source_id) for record in records]
        for item in items:
            item.relevance_score = self.score_relevance(item)
        self._items.extend(items)
        self._processed_files.add(str(path.resolve()))
        return items

    def ingest_directory(self, source_id: str = None) -> dict:
        files_processed = 0
        items_ingested = 0
        errors: list[str] = []
        fallback_source = source_id or "source-unknown"
        for path in sorted(Path(self.watch_dir).glob("*")):
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in self._processed_files:
                continue
            files_processed += 1
            try:
                items = self.ingest_file(filepath=str(path), source_id=fallback_source)
                items_ingested += len(items)
            except Exception as exc:
                msg = f"{path.name}: {exc}"
                errors.append(msg)
                self._errors.append(msg)
        return {
            "files_processed": files_processed,
            "items_ingested": items_ingested,
            "errors": errors,
        }

    def score_relevance(self, item: OSINTItem) -> float:
        """
        Score relevance to Saudi national security priorities.

        Tactical context: prioritize reports tied to KSA territory, GCC stability,
        military/cyber escalation, and strategic maritime chokepoints.
        """
        text = f"{item.title} {item.content}".lower()
        score = 0.0

        if any(token in text for token in ("saudi arabia", "ksa", "gcc", "riyadh", "jeddah", "المملكة")):
            score += 0.3
        if any(token in text for token in ("military", "defense", "security", "army", "naval", "أمن", "عسكري")):
            score += 0.2
        if any(token in text for token in ("yemen", "hormuz", "oil", "drone", "bab el-mandeb", "red sea", "نفط")):
            score += 0.2

        reliability = self._source_reliability.get(item.source_id, SourceReliability.F_UNKNOWN)
        reliability_weight = {
            SourceReliability.A_RELIABLE: 1.0,
            SourceReliability.B_USUALLY_RELIABLE: 0.8,
            SourceReliability.C_FAIRLY_RELIABLE: 0.6,
            SourceReliability.D_NOT_USUALLY_RELIABLE: 0.4,
            SourceReliability.E_UNRELIABLE: 0.2,
            SourceReliability.F_UNKNOWN: 0.3,
        }[reliability]
        score *= reliability_weight

        now = datetime.now(timezone.utc)
        age = now - item.timestamp.astimezone(timezone.utc)
        if age.total_seconds() < 24 * 3600:
            score += 0.1
        elif age.total_seconds() < 7 * 24 * 3600:
            score += 0.05

        # Optional LLM refinement with sovereign local model if available.
        try:
            prompt = (
                "Rate this intelligence item's relevance to Saudi national security 0-10: "
                f"{item.title} - {item.summary or item.content[:280]}"
            )
            response = self.analyzer.orchestrator.process(
                QueryRequest(prompt=prompt, domain=TaskDomain.TACTICAL)
            )
            text_out = getattr(response, "text", "")
            if text_out and "pending" not in text_out.lower():
                import re

                match = re.search(r"(\d+(?:\.\d+)?)", text_out)
                if match:
                    llm_score = float(match.group(1)) / 10.0
                    score = (score * 0.7) + (llm_score * 0.3)
        except Exception:
            pass

        return round(clamp(score, 0.0, 1.0), 3)

    def get_ingestion_stats(self) -> dict:
        return {
            "watch_dir": self.watch_dir,
            "processed_files": len(self._processed_files),
            "items_ingested": len(self._items),
            "errors": list(self._errors),
        }

    @property
    def items(self) -> list[OSINTItem]:
        return list(self._items)
