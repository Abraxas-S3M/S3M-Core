"""Production dependency checks for Cortex (fail-loud, no silent fallbacks)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional


class ProductionDependencyError(RuntimeError):
    """Raised when a required security dependency is unavailable in production mode."""


@dataclass(frozen=True, slots=True)
class DependencyProbes:
    """Injectable probes for unit tests and air-gapped dev environments."""

    liboqs_available: Callable[[], bool]
    docker_available: Callable[[], bool]
    gvisor_available: Callable[[], bool]
    opa_available: Callable[[], bool]


def _default_probes() -> DependencyProbes:
    def _liboqs() -> bool:
        try:
            import oqs  # noqa: F401
        except ImportError:
            return False
        return True

    def _docker() -> bool:
        import shutil

        return shutil.which("docker") is not None

    def _gvisor() -> bool:
        import shutil

        return shutil.which("runsc") is not None

    def _opa() -> bool:
        import shutil

        return shutil.which("opa") is not None

    return DependencyProbes(
        liboqs_available=_liboqs,
        docker_available=_docker,
        gvisor_available=_gvisor,
        opa_available=_opa,
    )


def assert_production_dependencies(
    *,
    production_mode: bool,
    require_isolation: bool = True,
    probes: Optional[DependencyProbes] = None,
) -> Dict[str, bool]:
    """Refuse production startup when critical security dependencies are missing."""
    if not production_mode:
        return {"skipped": True}

    probes = probes or _default_probes()
    status = {
        "liboqs": probes.liboqs_available(),
        "docker": probes.docker_available(),
        "gvisor": probes.gvisor_available(),
        "opa": probes.opa_available(),
    }

    missing = []
    if not status["liboqs"]:
        missing.append("liboqs")
    if not status["docker"]:
        missing.append("docker")
    if require_isolation and not status["gvisor"]:
        missing.append("gvisor")
    if not status["opa"]:
        missing.append("opa")

    if missing:
        raise ProductionDependencyError(
            "production mode requires security dependencies: " + ", ".join(sorted(missing))
        )

    return status
