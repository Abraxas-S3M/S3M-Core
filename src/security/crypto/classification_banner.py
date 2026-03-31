"""Classification banner and response labeling utilities."""

from __future__ import annotations

import json
from typing import Any, Dict

from src.security.input_validator import InputValidator


class ClassificationBanner:
    """Injects operational classification labels into API responses."""

    def __init__(self, level: str = "UNCLASSIFIED - FOUO"):
        if not InputValidator.validate_classification(level):
            raise ValueError(f"Invalid classification level: {level}")
        self._level = level

    def get_level(self) -> str:
        return self._level

    def set_level(self, level: str) -> None:
        if not InputValidator.validate_classification(level):
            raise ValueError(f"Invalid classification level: {level}")
        self._level = level

    @staticmethod
    def is_valid_level(level: str) -> bool:
        return InputValidator.validate_classification(level)

    def inject_header(self, response: Any) -> Any:
        if hasattr(response, "headers") and response.headers is not None:
            response.headers["X-Classification"] = self._level

        if hasattr(response, "media_type") and str(getattr(response, "media_type", "")).startswith("application/json"):
            body = getattr(response, "body", None)
            if isinstance(body, (bytes, bytearray)):
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if isinstance(payload, dict) and "classification" not in payload:
                        payload["classification"] = self._level
                        response.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        response.headers["content-length"] = str(len(response.body))
                except Exception:
                    pass
        return response

    def get_banner_html(self) -> str:
        color = "#5cb85c"  # Green (UNCLASSIFIED)
        if "FOUO" in self._level:
            color = "#f0ad4e"  # Amber
        if "SECRET" in self._level:
            color = "#d9534f"  # Red
        return (
            "<div class=\"classification-banner\" "
            f"style=\"background:#111;padding:8px 12px;color:{color};"
            "font-weight:bold;text-align:center;border-bottom:1px solid #333;\">"
            f"{self._level}</div>"
        )

    @staticmethod
    def validate_response(response_data: Dict[str, Any]) -> bool:
        return isinstance(response_data, dict) and "classification" in response_data
