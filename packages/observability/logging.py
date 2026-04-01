"""Structured JSON logging for provider integrations with secret redaction."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict


class StructuredLogger:
    """Emit provider-aware JSON logs without exposing secrets."""

    SECRET_KEYS = {"authorization", "x-api-key", "token", "secret", "password", "credential"}

    def __init__(self, name: str = "s3m.integration") -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def _redact(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for key, value in payload.items():
            if any(secret_key in key.lower() for secret_key in self.SECRET_KEYS):
                output[key] = "***REDACTED***"
            elif isinstance(value, dict):
                output[key] = self._redact(value)
            else:
                output[key] = value
        return output

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **kwargs,
        }
        clean = self._redact(payload)
        message = json.dumps(clean, default=str)
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message)

    def info(self, payload: Dict[str, Any]) -> None:
        self.log("info", payload.get("event", "integration_event"), **payload)

    def warning(self, payload: Dict[str, Any]) -> None:
        self.log("warning", payload.get("event", "integration_warning"), **payload)

    def error(self, payload: Dict[str, Any]) -> None:
        self.log("error", payload.get("event", "integration_error"), **payload)
