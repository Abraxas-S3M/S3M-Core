"""Document and imagery processing for multimodal commander uploads.

Military context:
Uploaded intelligence documents and sensor imagery are normalized into actionable
text and entities so commanders can rapidly route decisions across S3M layers.
"""

from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Dict, List

from src.threat_detection.object_detector import ObjectDetector


class DocumentProcessor:
    """Process PDF, spreadsheet, and image uploads in offline mode."""

    def __init__(self):
        self.detector = ObjectDetector(model_path="models/yolov8n-military.pt")

    @staticmethod
    def _detect_language(text: str) -> str:
        return "ar" if any(0x0600 <= ord(ch) <= 0x06FF for ch in text) else "en"

    @staticmethod
    def _extract_entities(text: str) -> List[dict]:
        entities: List[dict] = []
        for m in re.finditer(r"\b[A-Z]{2,}-\d+\b", text):
            entities.append({"type": "unit", "value": m.group(0)})
        for m in re.finditer(r"\b\d{3,6}\s*,\s*\d{3,6}\b", text):
            entities.append({"type": "grid", "value": m.group(0)})
        return entities

    @staticmethod
    def _summary(text: str) -> str:
        clean = re.sub(r"\s+", " ", text).strip()
        return clean[:300] if clean else "No textual content extracted"

    def process_pdf(self, file_path: str) -> dict:
        """Extract text from PDF using available local parser backends."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)

        text = ""
        pages = 0
        try:
            import pdfplumber  # type: ignore

            with pdfplumber.open(str(path)) as pdf:
                pages = len(pdf.pages)
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:
            try:
                from pypdf import PdfReader  # type: ignore

                reader = PdfReader(str(path))
                pages = len(reader.pages)
                text = "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception:
                try:
                    from pdfminer.high_level import extract_text  # type: ignore

                    text = extract_text(str(path))
                    pages = max(1, text.count("\f"))
                except Exception:
                    raw = path.read_bytes()
                    text = raw.decode("utf-8", errors="ignore")[:8000]
                    pages = 1

        lang = self._detect_language(text)
        return {
            "text": text,
            "pages": pages,
            "language": lang,
            "summary": self._summary(text),
            "entities": self._extract_entities(text),
        }

    def process_spreadsheet(self, file_path: str) -> dict:
        """Process CSV/XLSX and infer data domain from headers."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)

        rows: List[List] = []
        columns: List[str] = []
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                for idx, row in enumerate(reader):
                    if idx == 0:
                        columns = [str(c) for c in row]
                    else:
                        rows.append(row)
        else:
            try:
                import openpyxl  # type: ignore

                wb = openpyxl.load_workbook(str(path), read_only=True)
                sheet = wb.active
                for idx, row in enumerate(sheet.iter_rows(values_only=True)):
                    row_vals = ["" if v is None else v for v in row]
                    if idx == 0:
                        columns = [str(c) for c in row_vals]
                    else:
                        rows.append(row_vals)
            except Exception as exc:
                raise RuntimeError(f"Unable to process spreadsheet: {exc}") from exc

        h = " ".join(c.lower() for c in columns)
        detected = "unknown"
        if any(k in h for k in ["lat", "lon", "position"]):
            detected = "geospatial"
        elif any(k in h for k in ["name", "rank", "unit"]):
            detected = "personnel"
        elif any(k in h for k in ["asset", "maintenance", "rul"]):
            detected = "maintenance"
        elif any(k in h for k in ["threat", "alert", "severity"]):
            detected = "threat"
        elif any(k in h for k in ["supply", "inventory", "quantity"]):
            detected = "logistics"

        return {
            "data": rows,
            "columns": columns,
            "rows": len(rows),
            "detected_type": detected,
            "summary": f"Detected {detected} data with {len(rows)} rows.",
        }

    def process_image(self, file_path: str) -> dict:
        """Run object detection and generate tactical image description."""
        detections = self.detector.detect(file_path)
        items = [
            {"class_name": d.class_name, "confidence": d.confidence, "bbox": d.bbox_xyxy}
            for d in detections
        ]
        if items:
            desc = f"Detected {len(items)} objects: " + ", ".join(i["class_name"] for i in items)
        else:
            desc = "No tactical objects detected in uploaded image."
        return {"detections": items, "description": desc}
