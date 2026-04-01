from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from src.apps.intel.models import OSINTItem, SourceReliability
from src.apps.intel.osint.ingester import OSINTIngester


def _sample_record(title: str, content: str) -> dict:
    return {
        "title": title,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "url": "offline://sample",
        "region": "Arabian Peninsula",
        "topic": "regional_stability",
    }


def test_ingest_file_json_returns_items(tmp_path: Path) -> None:
    watch = tmp_path / "incoming"
    watch.mkdir()
    payload = [_sample_record("Saudi naval update", "Military patrol expanded in GCC waters.")]
    path = watch / "batch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ingester = OSINTIngester(watch_dir=str(watch))
    items = ingester.ingest_file(str(path), source_id="src-json")
    assert len(items) == 1
    assert isinstance(items[0], OSINTItem)


def test_ingest_file_csv_format(tmp_path: Path) -> None:
    watch = tmp_path / "incoming"
    watch.mkdir()
    path = watch / "batch.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "content", "timestamp", "url", "region", "topic"])
        writer.writeheader()
        writer.writerow(_sample_record("Hormuz watch", "Security concern near Strait of Hormuz."))
    ingester = OSINTIngester(watch_dir=str(watch))
    items = ingester.ingest_file(str(path), source_id="src-csv")
    assert len(items) == 1
    assert items[0].title == "Hormuz watch"


def test_ingest_file_txt_format(tmp_path: Path) -> None:
    watch = tmp_path / "incoming"
    watch.mkdir()
    path = watch / "batch.txt"
    path.write_text("Drone alert near border.\nPeace meeting announced.", encoding="utf-8")
    ingester = OSINTIngester(watch_dir=str(watch))
    items = ingester.ingest_file(str(path), source_id="src-txt")
    assert len(items) >= 2


def test_score_relevance_high_for_saudi_military() -> None:
    ingester = OSINTIngester()
    ingester.set_source_reliability("src-a", SourceReliability.A_RELIABLE)
    item = OSINTItem(
        item_id="i1",
        source_id="src-a",
        timestamp=datetime.now(timezone.utc),
        title="Saudi Arabia military readiness update",
        content="Defense forces in GCC conduct naval security operations near Hormuz.",
        language="en",
        url=None,
        regions=["Arabian Peninsula"],
        topics=["maritime_security"],
    )
    score = ingester.score_relevance(item)
    assert score >= 0.5


def test_score_relevance_low_for_unrelated_item() -> None:
    ingester = OSINTIngester()
    item = OSINTItem(
        item_id="i2",
        source_id="unknown",
        timestamp=datetime.now(timezone.utc),
        title="Local festival opens downtown",
        content="Cultural event with no defense relevance.",
        language="en",
        url=None,
        regions=["Global"],
        topics=["culture"],
    )
    score = ingester.score_relevance(item)
    assert score <= 0.3


def test_ingest_directory_processes_multiple_files(tmp_path: Path) -> None:
    watch = tmp_path / "incoming"
    watch.mkdir()
    (watch / "a.txt").write_text("Security alert one.", encoding="utf-8")
    (watch / "b.txt").write_text("Security alert two.", encoding="utf-8")
    ingester = OSINTIngester(watch_dir=str(watch))
    result = ingester.ingest_directory(source_id="src-dir")
    assert result["files_processed"] == 2
    assert result["items_ingested"] >= 2
