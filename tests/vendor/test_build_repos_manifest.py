from __future__ import annotations

from pathlib import Path

import yaml

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.vendor.build_repos_manifest import build_entries, write_manifest_files


def _write_manifest(
    root: Path,
    *,
    domain: str,
    slug: str,
    source_url: str,
    name: str = "sample",
    license_name: str = "MIT",
) -> None:
    manifest_path = root / "packages" / "integrations" / domain / slug / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "domain": domain,
                "slug": slug,
                "source_url": source_url,
                "name": name,
                "license": license_name,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_valid_github_urls_are_included(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        domain="autonomy",
        slug="stable-baselines3",
        source_url="https://github.com/DLR-RM/stable-baselines3",
        name="stable-baselines3",
        license_name="MIT",
    )
    included, skipped = build_entries(tmp_path / "packages" / "integrations")

    assert len(included) == 1
    assert included[0].domain == "autonomy"
    assert included[0].slug == "stable-baselines3"
    assert included[0].source_url == "https://github.com/DLR-RM/stable-baselines3"
    assert included[0].name == "stable-baselines3"
    assert skipped == []


def test_missing_or_non_github_urls_are_skipped(tmp_path: Path) -> None:
    _write_manifest(tmp_path, domain="cyber", slug="a", source_url="")
    _write_manifest(tmp_path, domain="cyber", slug="b", source_url="https://example.com/project")

    included, skipped = build_entries(tmp_path / "packages" / "integrations")

    assert included == []
    reasons = {entry.slug: entry.reason for entry in skipped}
    assert reasons["a"] == "missing source_url"
    assert reasons["b"] == "non-github source"


def test_placeholder_text_is_filtered(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        domain="interop",
        slug="placeholder-entry",
        source_url="Search related OpenC2 repos",
    )

    included, skipped = build_entries(tmp_path / "packages" / "integrations")

    assert included == []
    assert len(skipped) == 1
    assert skipped[0].reason == "placeholder source text"


def test_output_format_matches_spec(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        domain="autonomy",
        slug="ray-with-rllib",
        source_url="https://github.com/ray-project/ray",
        name="ray (with RLlib)",
        license_name="Apache 2.0",
    )

    included, skipped = build_entries(tmp_path / "packages" / "integrations")
    output_path = tmp_path / "scripts" / "vendor" / "repos.txt"
    repos_path, skipped_path = write_manifest_files(output_path, included, skipped)

    repos_lines = repos_path.read_text(encoding="utf-8").splitlines()
    assert repos_lines[0] == "# S3M Vendor Repos Manifest"
    assert repos_lines[1] == "# Auto-generated from packages/integrations/*/*/manifest.yaml"
    assert repos_lines[2] == "# Format: domain|slug|url|license|name"
    assert repos_lines[3] == "# Total entries: 1"
    assert repos_lines[4].startswith("# Generated: ")
    assert repos_lines[5] == "autonomy|ray-with-rllib|https://github.com/ray-project/ray|Apache 2.0|ray (with RLlib)"

    skipped_lines = skipped_path.read_text(encoding="utf-8").splitlines()
    assert skipped_lines[0] == "# S3M Vendor Repos Skipped"
    assert skipped_lines[3] == "# Total skipped: 0"

