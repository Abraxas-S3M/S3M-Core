"""Build-policy tests for Cortex customer Dockerfiles."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_assert_no_offensive_passes_without_offensive_tree(tmp_path: Path) -> None:
    root = tmp_path / "opt"
    (root / "services" / "cyber").mkdir(parents=True)
    (root / "services" / "cyber" / "soc_manager.py").write_text("# ok\n", encoding="utf-8")
    script = REPO_ROOT / "docker/cortex/scripts/assert_no_offensive.sh"
    proc = subprocess.run(
        ["bash", str(script)],
        check=False,
        env={"CORTEX_APP_ROOT": str(root), "S3M_BUILD_PROFILE": "customer"},
    )
    assert proc.returncode == 0


def test_assert_no_offensive_fails_when_offensive_present(tmp_path: Path) -> None:
    offensive = tmp_path / "services/cyber/offensive"
    offensive.mkdir(parents=True)
    (offensive / "caldera_bridge.py").write_text("# forbidden\n", encoding="utf-8")
    script = REPO_ROOT / "docker/cortex/scripts/assert_no_offensive.sh"
    proc = subprocess.run(
        ["bash", str(script)],
        check=False,
        env={"CORTEX_APP_ROOT": str(tmp_path), "S3M_BUILD_PROFILE": "customer"},
    )
    assert proc.returncode == 1
