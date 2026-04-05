"""Weapon payload adapters for tactical engagement simulations."""

from __future__ import annotations

from src.platforms.common import AuthorizationType, OperatorAuthorization, PayloadState, Track


class _BaseWeaponAdapter:
    """Shared payload behavior for offline fire-control adapter tests."""

    def __init__(self, payload_id: str, ammo_count: int) -> None:
        self.payload_id = payload_id
        self._connected = False
        self._ammo_count = ammo_count

    def connect(self) -> bool:
        self._connected = True
        return True

    def read_state(self) -> PayloadState:
        return PayloadState(payload_id=self.payload_id, ammo_count=self._ammo_count, connected=self._connected)


class RCWS127Adapter(_BaseWeaponAdapter):
    """Remote weapon station adapter for 12.7mm payload emulation."""

    def __init__(self, payload_id: str) -> None:
        super().__init__(payload_id=payload_id, ammo_count=400)


class RCWS145Adapter(_BaseWeaponAdapter):
    """Remote weapon station adapter for 14.5mm payload emulation."""

    def __init__(self, payload_id: str) -> None:
        super().__init__(payload_id=payload_id, ammo_count=250)


class SICHAdapter(_BaseWeaponAdapter):
    """SICH payload adapter for short-range direct-fire emulation."""

    def __init__(self, payload_id: str) -> None:
        super().__init__(payload_id=payload_id, ammo_count=120)


class OrionZU23Adapter(_BaseWeaponAdapter):
    """Orion ZU-23 adapter with target queue for engagement sequencing."""

    def __init__(self, payload_id: str) -> None:
        super().__init__(payload_id=payload_id, ammo_count=80)
        self._target_queue: list[Track] = []

    def queue_target(self, track: Track) -> bool:
        if not self._connected:
            return False
        self._target_queue.append(track)
        return True

    def get_queue(self) -> list[Track]:
        return list(self._target_queue)


class MANPADSAdapter(_BaseWeaponAdapter):
    """MANPADS adapter enforcing explicit operator engage authorization."""

    def __init__(self, payload_id: str) -> None:
        super().__init__(payload_id=payload_id, ammo_count=2)

    def operator_authorized_action(self, auth: OperatorAuthorization) -> bool:
        if auth.auth_type != AuthorizationType.ENGAGE:
            return False
        if self._ammo_count <= 0:
            return False
        self._ammo_count -= 1
        return True
