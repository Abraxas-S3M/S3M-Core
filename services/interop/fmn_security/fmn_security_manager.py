"""FMN security manager for coalition interoperability services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from services.interop.fmn_security.coalition_identity import CoalitionIdentityProvider
from services.interop.fmn_security.security_labels import NATOSecurityLabel, normalize_classification

_MESSAGE_LABEL_KEY = "_fmn_security_label"
_DATA_LABEL_KEY = "security_label"

_CLEARANCE_ORDER = {
    "NATO UNCLASSIFIED": 0,
    "NATO RESTRICTED": 1,
    "NATO CONFIDENTIAL": 2,
    "NATO SECRET": 3,
    "COSMIC TOP SECRET": 4,
}


def _load_fmn_config(path: str | Path = "configs/security.yaml") -> dict[str, Any]:
    config_path = Path(path)
    defaults: dict[str, Any] = {
        "classification_default": "NATO UNCLASSIFIED",
        "releasable_to_default": ["SAU"],
        "enforce_labels": False,
        "certificate_store": "configs/security/coalition_certs/",
    }
    if not config_path.exists():
        return defaults
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    candidate = payload.get("fmn_security", {})
    if not isinstance(candidate, dict):
        return defaults
    merged = dict(defaults)
    merged.update(candidate)
    return merged


class FMNSecurityManager:
    """Integrate FMN labels and coalition identity policy checks."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        resolved_config = dict(_load_fmn_config())
        if config:
            resolved_config.update(config)
        self.config = resolved_config
        self.identity_provider = CoalitionIdentityProvider()
        self.default_label = NATOSecurityLabel(
            classification=str(self.config.get("classification_default", "NATO UNCLASSIFIED")),
            policy_identifier="NATO",
            releasable_to=list(self.config.get("releasable_to_default", ["SAU"])),
            caveats=[],
        )

    def label_message(self, message: str, classification: str, releasable_to: list[str]) -> str:
        """Attach NATO FMN label to an interop payload for coalition release."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        if not isinstance(releasable_to, list) or not releasable_to:
            raise ValueError("releasable_to must include at least one nation")

        label = NATOSecurityLabel(
            classification=classification,
            policy_identifier="NATO",
            releasable_to=releasable_to,
            caveats=[],
        )
        payload = {
            "message": message,
            _MESSAGE_LABEL_KEY: label.build_label(),
        }
        return json.dumps(payload, separators=(",", ":"))

    def validate_incoming(self, message: str) -> tuple[bool, str]:
        """Validate FMN label presence and structure on incoming payloads."""
        if not isinstance(message, str) or not message.strip():
            return (False, "message must be a non-empty string")

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            if bool(self.config.get("enforce_labels", False)):
                return (False, "invalid JSON payload while labels enforced")
            return (True, "labels not enforced for non-JSON payload")

        if not isinstance(payload, dict):
            return (False, "payload must be a JSON object")

        raw_label = payload.get(_MESSAGE_LABEL_KEY)
        if raw_label is None:
            if bool(self.config.get("enforce_labels", False)):
                return (False, "missing FMN security label")
            return (True, "label missing but enforcement disabled")

        if not isinstance(raw_label, dict):
            return (False, "security label must be an object")

        try:
            NATOSecurityLabel(
                classification=str(raw_label.get("classification", "")),
                policy_identifier=str(raw_label.get("policy_identifier", "NATO")),
                releasable_to=list(raw_label.get("releasable_to", [])),
                caveats=list(raw_label.get("caveats", [])),
            )
        except Exception as exc:
            return (False, f"invalid security label: {exc}")

        return (True, "security label valid")

    def enforce_policy(self, operation: str, user: dict, data: dict) -> bool:
        """Enforce coalition authorization and FMN release policy constraints."""
        if not isinstance(operation, str) or not operation.strip():
            return False
        if not isinstance(user, dict) or not isinstance(data, dict):
            return False

        required_clearance = str(data.get("required_clearance", self.default_label.classification))
        if not self.identity_provider.check_authorization(user, required_clearance, operation):
            return False

        raw_label = data.get(_DATA_LABEL_KEY)
        if raw_label is None:
            return not bool(self.config.get("enforce_labels", False))
        if not isinstance(raw_label, dict):
            return False

        try:
            label = NATOSecurityLabel(
                classification=str(raw_label.get("classification", "")),
                policy_identifier=str(raw_label.get("policy_identifier", "NATO")),
                releasable_to=list(raw_label.get("releasable_to", [])),
                caveats=list(raw_label.get("caveats", [])),
            )
            user_clearance = normalize_classification(str(user.get("clearance", "")))
            required = normalize_classification(required_clearance)
        except Exception:
            return False

        if _CLEARANCE_ORDER[user_clearance] < _CLEARANCE_ORDER[required]:
            return False

        return label.validate_access(
            user_clearance=user_clearance,
            user_nation=str(user.get("nation", "")),
        )
