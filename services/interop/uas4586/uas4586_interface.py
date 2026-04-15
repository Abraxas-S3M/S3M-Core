"""High-level STANAG 4586 interoperability interface for S3M DroneOps."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
from typing import Any, Callable

from services.interop.uas4586.uas4586_messages import UAS4586MessageHandler

LOGGER = logging.getLogger(__name__)


class UAS4586Interface:
    """Provide LOI-gated UAS interoperability for coalition partner UCS nodes."""

    def __init__(self, config: dict | None = None, message_handler: UAS4586MessageHandler | None = None) -> None:
        cfg = dict(config or {})
        self.max_loi = int(cfg.get("max_loi", 3))
        self.publish_interval_seconds = int(cfg.get("publish_interval_seconds", 1))
        self.message_handler = message_handler or UAS4586MessageHandler()

        self._registered_uavs: dict[str, dict[str, Any]] = {}
        for entry in cfg.get("registered_uavs", []):
            if not isinstance(entry, dict):
                continue
            uav_id = str(entry.get("uav_id", "")).strip()
            if not uav_id:
                continue
            capabilities = entry.get("capabilities", [])
            if not isinstance(capabilities, list):
                capabilities = []
            self._registered_uavs[uav_id] = self._build_registration(
                uav_id=uav_id,
                uav_type=str(entry.get("uav_type", "unknown")),
                capabilities=[str(item) for item in capabilities],
            )

        self._published_xml: dict[str, list[str]] = {
            "vehicle_status": [],
            "payload_status": [],
            "isr_product": [],
            "payload_command": [],
        }
        self._payload_command_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._vehicle_command_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._rejected_vehicle_commands: list[dict[str, Any]] = []
        self._last_error: str | None = None

    def register_uav(self, uav_id: str, uav_type: str, capabilities: list[str]) -> dict:
        """Register UAV with STANAG 4586 capability metadata."""
        vehicle_id = self._require_non_empty_text(uav_id, "uav_id")
        vehicle_type = self._require_non_empty_text(uav_type, "uav_type")
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list of strings")
        normalized_capabilities = [self._require_non_empty_text(item, "capability") for item in capabilities]
        registration = self._build_registration(
            uav_id=vehicle_id,
            uav_type=vehicle_type,
            capabilities=normalized_capabilities,
        )
        self._registered_uavs[vehicle_id] = registration
        self._last_error = None
        return deepcopy(registration)

    def publish_vehicle_status(self, uav_id: str, status: dict) -> bool:
        """Publish STANAG 4586 VehicleStatusMessage for coalition monitoring."""
        return self._publish_with_loi(
            uav_id=uav_id,
            required_loi=2,
            message_type="vehicle_status",
            payload=status,
            builder=self.message_handler.build_vehicle_status,
        )

    def publish_payload_status(self, uav_id: str, payload: dict) -> bool:
        """Publish STANAG 4586 PayloadStatusMessage for ISR sensor state."""
        return self._publish_with_loi(
            uav_id=uav_id,
            required_loi=2,
            message_type="payload_status",
            payload=payload,
            builder=self.message_handler.build_payload_status,
        )

    def publish_isr_product(self, uav_id: str, product: dict) -> bool:
        """Publish STANAG 4586 ISRProductMessage for LOI 1/2 data receipt."""
        return self._publish_with_loi(
            uav_id=uav_id,
            required_loi=1,
            message_type="isr_product",
            payload=product,
            builder=self.message_handler.build_isr_product,
        )

    def receive_payload_command(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback to receive LOI 3 payload control commands."""
        if not callable(callback):
            raise ValueError("callback must be callable")
        self._payload_command_callbacks.append(callback)

    def receive_vehicle_command(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for vehicle control; commands are rejected at LOI <= 3."""
        if not callable(callback):
            raise ValueError("callback must be callable")
        self._vehicle_command_callbacks.append(callback)
        LOGGER.warning("UAS4586 LOI 4/5 vehicle control is disabled; callbacks will receive rejection notices")

    def handle_payload_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming payload command and dispatch to LOI 3 callbacks."""
        if not isinstance(command, dict):
            raise ValueError("command must be a dictionary")
        uav_id = self._require_non_empty_text(command.get("uav_id"), "uav_id")
        if not self._is_registered(uav_id):
            result = {"accepted": False, "reason": f"unknown_uav:{uav_id}"}
            self._last_error = result["reason"]
            return result
        if not self._supports_loi(uav_id, 3):
            result = {"accepted": False, "reason": f"uav_not_authorized_for_loi3:{uav_id}"}
            self._last_error = result["reason"]
            return result

        xml = self.message_handler.build_payload_command(uav_id, command)
        parsed = self.message_handler.parse_payload_command(xml)
        self._published_xml["payload_command"].append(xml)
        for callback in self._payload_command_callbacks:
            try:
                callback(deepcopy(parsed))
            except Exception as exc:  # pragma: no cover - defensive callback boundary
                LOGGER.warning("Payload command callback failed: %s", exc)
        self._last_error = None
        return {"accepted": True, "uav_id": uav_id, "command": parsed}

    def handle_vehicle_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Reject vehicle control until LOI 4/5 safety assurance is complete."""
        if not isinstance(command, dict):
            raise ValueError("command must be a dictionary")
        # Tactical safety note: LOI 4/5 are intentionally blocked to prevent
        # uncontrolled remote flight authority handover during coalition events.
        event = {
            "accepted": False,
            "reason": "LOI 4/5 vehicle control disabled pending safety validation",
            "command": deepcopy(command),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._rejected_vehicle_commands.append(event)
        self._last_error = event["reason"]
        LOGGER.warning("Rejected STANAG 4586 vehicle command: %s", command)
        for callback in self._vehicle_command_callbacks:
            try:
                callback(deepcopy(event))
            except Exception as exc:  # pragma: no cover - defensive callback boundary
                LOGGER.warning("Vehicle command callback failed: %s", exc)
        return event

    def get_registered_uavs(self) -> list[dict]:
        return [deepcopy(item) for item in self._registered_uavs.values()]

    def get_published_messages(self, message_type: str | None = None) -> dict[str, list[str]] | list[str]:
        if message_type is None:
            return {key: list(value) for key, value in self._published_xml.items()}
        if message_type not in self._published_xml:
            raise ValueError(f"unknown message_type: {message_type}")
        return list(self._published_xml[message_type])

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "max_loi": self.max_loi,
            "publish_interval_seconds": self.publish_interval_seconds,
            "registered_uav_count": len(self._registered_uavs),
            "registered_uavs": sorted(self._registered_uavs.keys()),
            "payload_command_callbacks": len(self._payload_command_callbacks),
            "vehicle_command_callbacks": len(self._vehicle_command_callbacks),
            "published_message_counts": {key: len(value) for key, value in self._published_xml.items()},
            "rejected_vehicle_commands": len(self._rejected_vehicle_commands),
            "last_error": self._last_error,
        }

    def _publish_with_loi(
        self,
        uav_id: str,
        required_loi: int,
        message_type: str,
        payload: dict,
        builder: Callable[[str, dict[str, Any]], str],
    ) -> bool:
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")
        vehicle_id = self._require_non_empty_text(uav_id, "uav_id")
        if not self._is_registered(vehicle_id):
            self._last_error = f"unknown_uav:{vehicle_id}"
            return False
        if not self._supports_loi(vehicle_id, required_loi):
            self._last_error = f"uav_not_authorized_for_loi{required_loi}:{vehicle_id}"
            return False
        try:
            xml = builder(vehicle_id, payload)
        except Exception as exc:
            self._last_error = str(exc)
            return False
        self._published_xml[message_type].append(xml)
        self._last_error = None
        return True

    def _is_registered(self, uav_id: str) -> bool:
        return uav_id in self._registered_uavs

    def _supports_loi(self, uav_id: str, loi: int) -> bool:
        registration = self._registered_uavs.get(uav_id, {})
        return int(registration.get("effective_loi", 0)) >= int(loi)

    def _build_registration(self, uav_id: str, uav_type: str, capabilities: list[str]) -> dict[str, Any]:
        normalized_caps: list[str] = []
        for item in capabilities:
            value = str(item).strip()
            if value and value not in normalized_caps:
                normalized_caps.append(value)

        requested_loi = self._extract_requested_loi(normalized_caps)
        effective_loi = min(self.max_loi, requested_loi)
        if effective_loi <= 0:
            effective_loi = min(self.max_loi, 3)

        return {
            "uav_id": uav_id,
            "uav_type": uav_type,
            "capabilities": normalized_caps,
            "effective_loi": effective_loi,
            "supported_loi": list(range(1, effective_loi + 1)),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _extract_requested_loi(capabilities: list[str]) -> int:
        highest = 0
        for capability in capabilities:
            token = capability.strip().upper().replace("-", "").replace("_", "")
            if token.startswith("LOI") and token[3:].isdigit():
                highest = max(highest, int(token[3:]))
            elif token.startswith("LEVEL") and token[5:].isdigit():
                highest = max(highest, int(token[5:]))
        return highest

    @staticmethod
    def _require_non_empty_text(value: Any, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required")
        return text
