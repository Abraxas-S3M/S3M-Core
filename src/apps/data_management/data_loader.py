"""Format-aware data loading utilities for dataset workflows."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.apps._shared import ensure_non_empty_text


class DataLoader:
    """Offline data loader supporting common tactical dataset formats."""

    def __init__(self) -> None:
        self._supported = {"csv", "json", "txt", "text", "images", "directory"}

    def _infer_format(self, filepath: str) -> str:
        path = Path(filepath)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix == ".json":
            return "json"
        if suffix in {".txt", ".md", ".log"}:
            return "text"
        if path.is_dir():
            return "images"
        return "text"

    def load(self, filepath: str, format: str = "auto") -> dict:
        path = ensure_non_empty_text(filepath, "filepath")
        fmt = ensure_non_empty_text(format, "format").lower()
        if fmt == "auto":
            fmt = self._infer_format(path)
        if fmt == "csv":
            payload = self.load_csv(path)
            return {"data": payload["data"], "format": "csv", "records": payload["records"], "columns": payload["columns"]}
        if fmt == "json":
            payload = self.load_json(path)
            columns = list(payload["data"][0].keys()) if isinstance(payload["data"], list) and payload["data"] else None
            return {"data": payload["data"], "format": "json", "records": payload["records"], "columns": columns}
        if fmt in {"images", "directory"}:
            payload = self.load_image_directory(path)
            return {"data": payload["files"], "format": "images", "records": payload["count"], "columns": None}
        if fmt in {"text", "txt"}:
            payload = self.load_text(path)
            return {"data": payload["text"], "format": "text", "records": payload["lines"], "columns": None}
        raise ValueError(f"Unsupported format: {fmt}")

    def load_csv(self, filepath: str, max_rows: int = None) -> dict:
        path = Path(ensure_non_empty_text(filepath, "filepath"))
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        try:
            import pandas as pd  # type: ignore

            df = pd.read_csv(path, nrows=max_rows)
            return {"data": df.values.tolist(), "columns": [str(col) for col in df.columns], "records": int(len(df))}
        except Exception:
            rows: List[List[Any]] = []
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                columns = next(reader, [])
                for row in reader:
                    rows.append(row)
                    if isinstance(max_rows, int) and max_rows > 0 and len(rows) >= max_rows:
                        break
            return {"data": rows, "columns": columns, "records": len(rows)}

    def load_json(self, filepath: str) -> dict:
        path = Path(ensure_non_empty_text(filepath, "filepath"))
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {filepath}")
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        records = len(payload) if isinstance(payload, list) else (len(payload.keys()) if isinstance(payload, dict) else 1)
        return {"data": payload, "records": int(records)}

    def load_image_directory(self, dirpath: str, extensions: List[str] = None) -> dict:
        path = Path(ensure_non_empty_text(dirpath, "dirpath"))
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"Directory not found: {dirpath}")
        exts = extensions or [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
        normalized = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in exts}
        files: List[str] = []
        counts: Dict[str, int] = {}
        for file_path in sorted(path.iterdir()):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix in normalized:
                files.append(str(file_path))
                counts[suffix] = counts.get(suffix, 0) + 1
        return {"files": files, "count": len(files), "extensions": counts}

    def load_text(self, filepath: str) -> dict:
        path = Path(ensure_non_empty_text(filepath, "filepath"))
        if not path.exists():
            raise FileNotFoundError(f"Text file not found: {filepath}")
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        return {"text": text, "lines": len(lines), "chars": len(text)}

    def _infer_dtype(self, values: List[str]) -> str:
        sample = [value for value in values if value not in {"", None}]
        if not sample:
            return "unknown"
        try:
            for value in sample:
                int(str(value))
            return "int"
        except Exception:
            pass
        try:
            for value in sample:
                float(str(value))
            return "float"
        except Exception:
            pass
        return "str"

    def get_schema(self, filepath: str, format: str = "auto") -> dict:
        path = ensure_non_empty_text(filepath, "filepath")
        fmt = ensure_non_empty_text(format, "format").lower()
        if fmt == "auto":
            fmt = self._infer_format(path)
        if fmt == "csv":
            csv_data = self.load_csv(path, max_rows=5)
            columns = csv_data["columns"]
            rows = csv_data["data"]
            col_specs = []
            for idx, name in enumerate(columns):
                samples = [row[idx] for row in rows if len(row) > idx][:5]
                col_specs.append({"name": name, "dtype": self._infer_dtype(samples), "sample_values": samples})
            return {"columns": col_specs}
        if fmt == "json":
            payload = self.load_json(path)["data"]
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                first = payload[0]
                cols = []
                for key, value in first.items():
                    cols.append({"name": str(key), "dtype": type(value).__name__, "sample_values": [value]})
                return {"columns": cols}
            if isinstance(payload, dict):
                cols = [{"name": str(k), "dtype": type(v).__name__, "sample_values": [v]} for k, v in payload.items()]
                return {"columns": cols}
            return {"columns": [{"name": "value", "dtype": type(payload).__name__, "sample_values": [payload]}]}
        if fmt in {"text", "txt"}:
            text = self.load_text(path)
            lines = text["text"].splitlines()[:5]
            return {"columns": [{"name": "text", "dtype": "str", "sample_values": lines}]}
        return {"columns": []}
