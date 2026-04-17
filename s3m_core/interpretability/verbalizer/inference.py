"""Real-time activation verbalizer monitoring for S3M inference.

Military/tactical context:
This monitor provides live cognitive audit trails and threat-oriented alerts
without altering primary-model outputs, preserving chain-of-command trust in
autonomous advisory behavior during mission execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, Sequence

import torch

from .model import ActivationVerbalizer


@dataclass(frozen=True)
class AVAlert:
    """Alert object emitted when verbalized cognition includes risky indicators."""

    position: int
    description: str
    matched_keywords: List[str]
    activation_norm: float


class ActivationHookManager(Protocol):
    """Protocol adapter for retrieving token-position activations."""

    def get_activation(self, token_position: int) -> Optional[torch.Tensor]:
        ...


class AVMonitor:
    """Monitor Activation Verbalizer outputs during primary-model generation."""

    def __init__(
        self,
        verbalizer: ActivationVerbalizer,
        hook_manager: ActivationHookManager,
        verbalize_every_n_tokens: int = 10,
        alert_keywords: List[str] = [
            "exploit",
            "bypass",
            "secret",
            "unauthorized",
            "manipulate",
            "deceive",
            "hack",
        ],
    ) -> None:
        if verbalize_every_n_tokens <= 0:
            raise ValueError("verbalize_every_n_tokens must be positive.")
        self.verbalizer = verbalizer
        self.hook_manager = hook_manager
        self.verbalize_every_n_tokens = verbalize_every_n_tokens

        default_arabic = ["اختراق", "تجاوز", "سري", "غير مصرح", "تلاعب", "خداع", "تهكير"]
        provided = [kw.strip() for kw in alert_keywords if kw.strip()]
        combined = list(dict.fromkeys([*provided, *default_arabic]))
        self.alert_keywords = combined

        self._narrative_entries: List[str] = []
        self._alerts: List[AVAlert] = []

    def monitor_step(self, token_position: int) -> Optional[AVAlert]:
        """Verbalize and scan periodic activations for risk keywords."""
        if token_position < 0:
            raise ValueError("token_position must be non-negative.")
        if token_position % self.verbalize_every_n_tokens != 0:
            return None

        activation = self._fetch_activation(token_position)
        if activation is None:
            return None

        description = self.verbalizer.verbalize(activation)
        narrative_line = f"[token {token_position}] {description}"
        self._narrative_entries.append(narrative_line)

        matched_keywords = self._match_keywords(description, self.alert_keywords)
        if not matched_keywords:
            return None

        alert = AVAlert(
            position=token_position,
            description=description,
            matched_keywords=matched_keywords,
            activation_norm=float(torch.norm(activation).item()),
        )
        self._alerts.append(alert)
        return alert

    def get_full_narrative(self) -> str:
        """Return concatenated thought narrative collected for the current response."""
        return "\n".join(self._narrative_entries)

    def get_alert_log(self) -> Sequence[AVAlert]:
        """Return immutable alert history for audit log export."""
        return tuple(self._alerts)

    def _fetch_activation(self, token_position: int) -> Optional[torch.Tensor]:
        accessor_names = (
            "get_activation",
            "get_activation_at",
            "get_latest_activation",
            "latest_activation_for_position",
        )
        for name in accessor_names:
            accessor = getattr(self.hook_manager, name, None)
            if accessor is None:
                continue
            try:
                value = accessor(token_position)
            except TypeError:
                value = accessor()
            if isinstance(value, torch.Tensor):
                return value.detach().to(dtype=torch.float32)
        fallback = getattr(self.hook_manager, "latest_activation", None)
        if isinstance(fallback, torch.Tensor):
            return fallback.detach().to(dtype=torch.float32)
        return None

    @staticmethod
    def _match_keywords(description: str, keywords: List[str]) -> List[str]:
        lowered = description.lower()
        matches: List[str] = []
        for keyword in keywords:
            if not keyword:
                continue
            probe = keyword.lower()
            if probe in lowered or keyword in description:
                matches.append(keyword)
        return matches
