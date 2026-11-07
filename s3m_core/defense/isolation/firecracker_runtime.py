"""Firecracker microVM runtime stub (not yet deployed on edge nodes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .sandbox_config import SandboxConfig

_FIRECRACKER_MESSAGE = (
    "Firecracker microVM isolation is not implemented in this build. "
    "Use runtime='gvisor' (default) or runtime='docker' with a hardened profile."
)


@dataclass(slots=True)
class FirecrackerRuntime:
    """
    Placeholder for Firecracker-backed agent cells.

    Tactical context:
    MicroVMs are the planned high-assurance tier; until wired, callers must not
    receive a fake handle that implies kernel-level separation exists.
    """

    def start_session_cell(
        self,
        *,
        session_id: str,
        image: str,
        config: SandboxConfig,
        scratch_mount: str,
        network_mode: str,
        extra_args: List[str],
    ) -> tuple[str, int]:
        _ = (session_id, image, config, scratch_mount, network_mode, extra_args)
        raise NotImplementedError(_FIRECRACKER_MESSAGE)
