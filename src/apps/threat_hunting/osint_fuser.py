"""OSINT fusion module for offline threat hunting workflows."""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any, List, Optional

from src.apps._shared import ensure_non_empty_text, utc_now_iso
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


_LOC_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\b")
_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")
_THREAT_PATTERN = re.compile(
    r"\b(attack|missile|drone|intrusion|cyber|bomb|smuggling|militia|threat|weapon)\b",
    re.IGNORECASE,
)


class OSINTFuser:
    """Ingest and analyze operator-provided OSINT files in air-gapped mode."""

    def __init__(self, data_dir: str = "data/osint/") -> None:
        if not isinstance(data_dir, str) or not data_dir.strip():
            raise ValueError("data_dir must be a non-empty string")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.orchestrator = Orchestrator()
        self._ingested: list[dict[str, Any]] = []
        self._analysis_count = 0

    def _extract_entities(self, text: str) -> list[dict[str, str]]:
        entities: list[dict[str, str]] = []
        for match in _LOC_PATTERN.findall(text):
            entities.append({"type": "location_or_org", "value": match})
        for match in _DATE_PATTERN.findall(text):
            entities.append({"type": "date", "value": match})
        for match in _THREAT_PATTERN.findall(text):
            entities.append({"type": "threat_indicator", "value": match.lower()})
        dedup = {(item["type"], item["value"]): item for item in entities}
        return list(dedup.values())

    def _read_path(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"OSINT file not found: {path}")
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(payload, ensure_ascii=False)
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                rows = [",".join(row) for row in reader]
            return "\n".join(rows)
        return path.read_text(encoding="utf-8")

    def ingest_file(self, filepath: str, source_name: str = "manual") -> dict:
        src = ensure_non_empty_text(source_name, "source_name")
        file_input = ensure_non_empty_text(filepath, "filepath")
        path = Path(file_input)
        if not path.is_absolute():
            path = self.data_dir / path
        content = self._read_path(path)
        lines = [line for line in content.splitlines() if line.strip()]
        entities = self._extract_entities(content)
        record = {
            "source": src,
            "path": str(path),
            "records": max(1, len(lines)),
            "entities_extracted": entities,
            "timestamp": utc_now_iso(),
        }
        self._ingested.append(record)
        return {
            "source": src,
            "records": record["records"],
            "entities_extracted": entities,
        }

    def analyze(self, query: str, context_files: Optional[List[str]] = None) -> dict:
        ask = ensure_non_empty_text(query, "query")
        context_parts: list[str] = []
        used_sources: list[str] = []
        for name in context_files or []:
            path = Path(name)
            if not path.is_absolute():
                path = self.data_dir / path
            try:
                content = self._read_path(path)
            except Exception:
                continue
            context_parts.append(content)
            used_sources.append(str(path))
        context = "\n\n".join(context_parts)[:4000]
        prompt = (
            "You are an intelligence analyst. Analyze the following OSINT data and answer: "
            f"{ask}. Context: {context}. Provide: 1) Key findings 2) Source reliability assessment "
            "3) Intelligence gaps 4) Recommended collection priorities. "
            "Classification: UNCLASSIFIED - FOUO."
        )
        analysis = "Analysis unavailable — LLM not loaded"
        confidence = 0.2
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "")
            if text and "not yet loaded" not in text.lower():
                analysis = text
                confidence = 0.7
        except Exception:
            pass
        self._analysis_count += 1
        return {
            "query": ask,
            "analysis": analysis,
            "confidence": confidence,
            "sources_used": used_sources,
            "timestamp": utc_now_iso(),
        }

    def generate_intel_report(self, topic: str, sources: Optional[List[str]] = None) -> str:
        subject = ensure_non_empty_text(topic, "topic")
        source_files = sources or [entry["path"] for entry in self.list_sources()]
        result = self.analyze(f"Generate intelligence report about: {subject}", source_files)
        if result["analysis"] != "Analysis unavailable — LLM not loaded":
            return result["analysis"]
        return (
            f"INTEL REPORT — {subject}\n"
            "Classification: UNCLASSIFIED - FOUO\n"
            f"Sources reviewed: {len(source_files)}\n"
            "LLM analysis unavailable; prioritize manual analyst review."
        )

    def list_sources(self) -> List[dict]:
        files: list[dict[str, Any]] = []
        for path in sorted(self.data_dir.glob("*")):
            if path.is_file():
                stat = path.stat()
                files.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "size_bytes": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )
        return files

    def get_stats(self) -> dict:
        return {
            "files_ingested": len(self._ingested),
            "analyses_performed": self._analysis_count,
            "source_directory": str(self.data_dir),
            "available_files": len(self.list_sources()),
        }

