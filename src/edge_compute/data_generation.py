"""Autonomous data generation with local knowledge-graph persistence."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from src.edge_compute.models import DatasetStrategy, GeneratedDataset

logger = logging.getLogger("s3m.edge.data_generation")


class KnowledgeGraphStore:
    """Simple SQLite-backed local graph store for offline edge nodes."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                name TEXT PRIMARY KEY
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                PRIMARY KEY (src, dst)
            )
            """
        )
        self._conn.commit()

    def add_entity(self, name: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO entities(name) VALUES (?)", (name,))
        self._conn.commit()

    def add_edge(self, src: str, dst: str, weight: float = 1.0) -> None:
        self.add_entity(src)
        self.add_entity(dst)
        self._conn.execute(
            "INSERT OR REPLACE INTO edges(src, dst, weight) VALUES (?, ?, ?)",
            (src, dst, float(weight)),
        )
        self._conn.commit()

    def stats(self) -> Dict[str, int]:
        cur = self._conn.cursor()
        entities = int(cur.execute("SELECT COUNT(1) FROM entities").fetchone()[0])
        edges = int(cur.execute("SELECT COUNT(1) FROM edges").fetchone()[0])
        return {"entities": entities, "edges": edges}

    def query_neighbors(self, entity_name: str, max_hops: int = 1) -> List[Dict[str, object]]:
        if max_hops <= 1:
            cur = self._conn.cursor()
            rows = cur.execute(
                "SELECT dst, weight FROM edges WHERE src = ? ORDER BY weight DESC LIMIT 100",
                (entity_name,),
            ).fetchall()
            return [{"entity": row[0], "weight": float(row[1]), "hops": 1} for row in rows]

        visited = {entity_name}
        frontier = {entity_name}
        out: List[Dict[str, object]] = []
        for hop in range(1, max_hops + 1):
            if not frontier:
                break
            nxt = set()
            for src in frontier:
                cur = self._conn.cursor()
                rows = cur.execute(
                    "SELECT dst, weight FROM edges WHERE src = ? ORDER BY weight DESC LIMIT 100",
                    (src,),
                ).fetchall()
                for dst, weight in rows:
                    if dst in visited:
                        continue
                    visited.add(dst)
                    nxt.add(dst)
                    out.append({"entity": dst, "weight": float(weight), "hops": hop})
            frontier = nxt
        return out

    def close(self) -> None:
        self._conn.close()


@dataclass
class ReplayBuffer:
    """Tracks classes already represented in generated replay sets."""

    fitted_classes: set[str] = field(default_factory=set)


class DataGenerationEngine:
    """Generate local datasets and maintain a minimal tactical knowledge graph."""

    def __init__(self, output_dir: str = "data/edge/generated/", kg_db_path: str = "data/edge/knowledge.db") -> None:
        self.output_dir = output_dir
        self.knowledge_graph = KnowledgeGraphStore(kg_db_path)
        self.replay = ReplayBuffer()
        self._datasets: List[GeneratedDataset] = []
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def list_generated(self) -> List[GeneratedDataset]:
        return list(self._datasets)

    def _write_dataset(self, strategy: DatasetStrategy, records: Sequence[Dict[str, object]]) -> GeneratedDataset:
        dataset_id = f"ds-{uuid.uuid4().hex[:12]}"
        file_path = os.path.join(self.output_dir, f"{dataset_id}.jsonl")
        with open(file_path, "w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        size = os.path.getsize(file_path)
        dataset = GeneratedDataset(
            dataset_id=dataset_id,
            strategy=strategy,
            record_count=len(records),
            file_path=file_path,
            file_size_bytes=size,
        )
        self._datasets.append(dataset)
        return dataset

    def generate_contrastive_dataset(self, records: Sequence[Dict[str, object]]) -> GeneratedDataset:
        safe_records: List[Dict[str, object]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "unknown"))
            self.replay.fitted_classes.add(label)
            text = str(item.get("text", ""))
            safe_records.append({"text": text, "label": label, "hard_negative": f"not::{label}"})
            self.knowledge_graph.add_entity(label)
        return self._write_dataset(DatasetStrategy.CONTRASTIVE, safe_records)

    def discover_relationships(self, min_count: int = 3, min_pmi: float = 1.0) -> int:
        # Tactical-safe heuristic: create deterministic local links, no external calls.
        _ = max(1, int(min_count))
        _ = max(0.0, float(min_pmi))
        labels = sorted(self.replay.fitted_classes)
        added = 0
        for i in range(0, max(0, len(labels) - 1)):
            src = labels[i]
            dst = labels[i + 1]
            self.knowledge_graph.add_edge(src, dst, weight=1.25)
            added += 1
        return added

    def health_check(self) -> Dict[str, object]:
        kg = self.knowledge_graph.stats()
        return {
            "status": "operational",
            "datasets_generated": len(self._datasets),
            "output_dir": self.output_dir,
            "kg_entities": kg["entities"],
            "kg_edges": kg["edges"],
            "replay_classes": len(self.replay.fitted_classes),
        }
