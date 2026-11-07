"""Build-profile gates for customer deliverables vs range/dev tooling."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from src.build_profile import BuildProfile, get_build_profile, offensive_tooling_enabled

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IN_NAMES = ("SealedTunnel", "STLink", "XOTC", "Terniion")


def _purge_offensive_modules() -> None:
    for name in list(sys.modules):
        if name == "services.cyber.offensive" or name.startswith(
            "services.cyber.offensive."
        ):
            del sys.modules[name]


def test_default_profile_is_dev_under_pytest() -> None:
    assert get_build_profile() == BuildProfile.DEV
    assert offensive_tooling_enabled() is True


def test_customer_profile_blocks_offensive_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3M_BUILD_PROFILE", "customer")
    _purge_offensive_modules()
    with pytest.raises(ImportError, match="customer"):
        importlib.import_module("services.cyber.offensive")


def test_range_profile_allows_caldera_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3M_BUILD_PROFILE", "range")
    _purge_offensive_modules()
    mod = importlib.import_module("services.cyber.offensive")
    assert hasattr(mod, "CalderaBridge")


def test_customer_profile_disables_offensive_tooling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3M_BUILD_PROFILE", "customer")
    assert offensive_tooling_enabled() is False


def test_workspace_routes_register_caldera_only_when_enabled() -> None:
    """Caldera imports and endpoints must sit behind offensive_tooling_enabled()."""
    source = (ROOT / "src/api/gui_bridge/workspace_routes.py").read_text(
        encoding="utf-8"
    )
    assert "if offensive_tooling_enabled():" in source
    assert source.index("if offensive_tooling_enabled():") < source.index(
        "from services.cyber.offensive.caldera_bridge import CalderaBridge"
    )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("from services.cyber.offensive"):
            assert line.startswith("    "), "Caldera import must be nested in profile guard"


def test_no_xiid_product_identifiers_in_source_tree() -> None:
    import ast

    skip_dirs = {"docs", "__pycache__", ".git"}
    skip_prefixes = (
        Path("src/security/zkn"),
        Path("src/cortex/broker.py"),
    )

    violations: list[str] = []

    def _is_excluded(path: Path) -> bool:
        rel = path.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & skip_dirs:
            return True
        for prefix in skip_prefixes:
            prefix_rel = prefix
            if str(prefix).endswith(".py"):
                if rel.as_posix() == prefix.as_posix():
                    return True
            elif rel.as_posix().startswith(prefix.as_posix()):
                return True
        if "packages/integrations" in rel.as_posix() and "xiid" in rel.as_posix().lower():
            return True
        return False

    class _Visitor(ast.NodeVisitor):
        def __init__(self, relpath: str) -> None:
            self.relpath = relpath

        def _check(self, name: str, lineno: int) -> None:
            if any(token in name for token in FORBIDDEN_IN_NAMES):
                violations.append(f"{self.relpath}:{lineno}: {name}")

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._check(node.name, node.lineno)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._check(node.name, node.lineno)
            for arg in node.args.args + node.args.kwonlyargs:
                self._check(arg.arg, node.lineno)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._check(target.id, node.lineno)
            self.generic_visit(node)

    for path in ROOT.rglob("*.py"):
        if _is_excluded(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        _Visitor(path.relative_to(ROOT).as_posix()).visit(tree)

    assert not violations, "forbidden XiiD product identifiers:\n" + "\n".join(violations)
