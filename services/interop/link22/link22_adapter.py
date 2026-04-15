"""Link 22 (STANAG 5522) adapter contract for future classified integration.

Military/tactical context:
This stub establishes a stable API for Link 22 tactical data-link integration so
coalition maritime and air C2 pipelines can be wired now and upgraded later when
classified implementation details become available.
"""

from __future__ import annotations

import logging


class Link22Adapter:
    """Stubbed Link 22 adapter preserving the future integration API surface."""

    SUPPORTED_MESSAGES = [
        "F.1 - Unit Position",
        "F.2 - Air Track",
        "F.3 - Surface Track",
        "F.5 - EW Track",
        "F.6 - ACCS Report",
    ]

    # Tactical mapping baseline used by downstream S3M consumers before
    # classified STANAG parsing is available in production.
    F_SERIES_TO_S3M_ENTITY_TYPES = {
        "F.1 - Unit Position": ["FRIENDLY_UGV", "ENEMY_UGV"],
        "F.2 - Air Track": ["FRIENDLY_UAV", "ENEMY_UAV"],
        "F.3 - Surface Track": ["FRIENDLY_SHIP", "ENEMY_SHIP"],
        "F.5 - EW Track": ["ENEMY_UAV", "ENEMY_UGV"],
        "F.6 - ACCS Report": ["CIVILIAN", "UNKNOWN"],
    }

    def __init__(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError("Link22Adapter config must be a dictionary")
        self.config = dict(config)
        self.mode = str(self.config.get("mode", "stub")).strip().lower() or "stub"
        self._connected_endpoint: str | None = None
        self.logger = logging.getLogger(__name__)

    def connect(self, network_address: str) -> bool:
        """Attempt Link 22 transport initialization.

        Tactical note:
        Real transport/session setup remains blocked until classified Link 22
        interface controls are available in the deployment enclave.
        """
        if not isinstance(network_address, str):
            raise ValueError("network_address must be a string")
        self._connected_endpoint = network_address.strip() or None
        self.mode = "stub"
        self.logger.warning("Link 22 connection requires classified interface — stub mode active")
        return False

    def receive_tracks(self) -> list[dict]:
        """Receive Link 22 tracks.

        Tactical note:
        When the real Link 22 interface is available, this method will parse
        F-series tactical messages and normalize them to S3M track entities.
        """
        if self.mode == "stub":
            return []
        return []

    def publish_track(self, track: dict) -> bool:
        """Publish a single S3M track to Link 22 transport.

        Tactical note:
        In stub mode we retain the API call and log outgoing tracks so tactical
        workflow integration can be validated without classified transport.
        """
        if not isinstance(track, dict):
            raise ValueError("track must be a dictionary")
        if self.mode == "stub":
            self.logger.info("Link 22 stub publish requested for track: %s", track)
            return False
        return False

    def get_supported_messages(self) -> list[str]:
        """Return currently modeled Link 22 F-series messages."""
        return list(self.SUPPORTED_MESSAGES)

    def health_check(self) -> dict:
        """Report adapter health for orchestration and readiness checks."""
        return {"status": "stub", "reason": "Classified interface not available"}

    def get_message_entity_mapping(self) -> dict[str, list[str]]:
        """Return F-series to S3M entity mapping used by this adapter contract."""
        return {message: list(entity_types) for message, entity_types in self.F_SERIES_TO_S3M_ENTITY_TYPES.items()}
