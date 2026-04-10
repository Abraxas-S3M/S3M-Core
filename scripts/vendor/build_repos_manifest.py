#!/usr/bin/env python3
"""Build the canonical vendor repository manifest for Hetzner clone staging.

Military/tactical context:
    S3M needs deterministic inventory of approved upstream code sources so
    disconnected deployment teams can stage vendor dependencies into the
    sovereign BackBlaze vault without ad-hoc internet browsing.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger("s3m.vendor")

PLACEHOLDER_TOKENS: tuple[str, ...] = ("search", "related", "references in")


@dataclass(frozen=True)
class RepoEntry:
    """One valid GitHub repository extracted from an integration manifest."""

    domain: str
    slug: str
    source_url: str
    license_name: str
    name: str


@dataclass(frozen=True)
class SkippedEntry:
    """One excluded manifest row and the tactical reason it was skipped."""

    domain: str
    slug: str
    source_url: str
    reason: str
    manifest_path: Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_output_path() -> Path:
    return _project_root() / "scripts" / "vendor" / "repos.txt"


def _clean_field(value: Any, *, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    sanitized = text.replace("\n", " ").replace("\r", " ").replace("|", "/")
    return " ".join(sanitized.split())


def _skip_reason(source_url: str) -> str | None:
    lowered = source_url.lower()
    if not source_url:
        return "missing source_url"
    if any(token in lowered for token in PLACEHOLDER_TOKENS):
        return "placeholder source text"
    if "github.com" not in lowered:
        return "non-github source"
    return None


def _parse_manifest(manifest_path: Path) -> tuple[RepoEntry | None, SkippedEntry | None]:
    raw: dict[str, Any] = {}
    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if isinstance(payload, dict):
            raw = payload
    except yaml.YAMLError:
        domain = manifest_path.parent.parent.name
        slug = manifest_path.parent.name
        skipped = SkippedEntry(
            domain=domain,
            slug=slug,
            source_url="",
            reason="invalid yaml",
            manifest_path=manifest_path,
        )
        return None, skipped

    domain = _clean_field(raw.get("domain"), fallback=manifest_path.parent.parent.name) or manifest_path.parent.parent.name
    slug = _clean_field(raw.get("slug"), fallback=manifest_path.parent.name) or manifest_path.parent.name
    source_url = _clean_field(raw.get("source_url"))
    reason = _skip_reason(source_url)
    if reason:
        skipped = SkippedEntry(
            domain=domain,
            slug=slug,
            source_url=source_url,
            reason=reason,
            manifest_path=manifest_path,
        )
        return None, skipped

    repo = RepoEntry(
        domain=domain,
        slug=slug,
        source_url=source_url,
        license_name=_clean_field(raw.get("license"), fallback="unknown") or "unknown",
        name=_clean_field(raw.get("name"), fallback=slug) or slug,
    )
    return repo, None


def build_entries(integrations_root: Path) -> tuple[list[RepoEntry], list[SkippedEntry]]:
    """Scan integration manifests and split included versus skipped rows."""

    manifests = sorted(integrations_root.glob("*/*/manifest.yaml"))
    included: list[RepoEntry] = []
    skipped: list[SkippedEntry] = []
    for manifest_path in manifests:
        repo, rejected = _parse_manifest(manifest_path)
        if repo is not None:
            included.append(repo)
        if rejected is not None:
            skipped.append(rejected)

    included.sort(key=lambda item: (item.domain, item.slug))
    skipped.sort(key=lambda item: (item.domain, item.slug))
    return included, skipped


def write_manifest_files(output_path: Path, included: list[RepoEntry], skipped: list[SkippedEntry]) -> tuple[Path, Path]:
    """Write included and skipped manifests to deterministic text files."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    skipped_path = output_path.parent / "repos_skipped.txt"
    generated_at = datetime.now(tz=timezone.utc).isoformat()

    lines: list[str] = [
        "# S3M Vendor Repos Manifest",
        "# Auto-generated from packages/integrations/*/*/manifest.yaml",
        "# Format: domain|slug|url|license|name",
        f"# Total entries: {len(included)}",
        f"# Generated: {generated_at}",
    ]
    lines.extend(
        f"{entry.domain}|{entry.slug}|{entry.source_url}|{entry.license_name}|{entry.name}"
        for entry in included
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    skipped_lines: list[str] = [
        "# S3M Vendor Repos Skipped",
        "# Auto-generated from packages/integrations/*/*/manifest.yaml",
        "# Format: domain|slug|reason|source_url|manifest_path",
        f"# Total skipped: {len(skipped)}",
        f"# Generated: {generated_at}",
    ]
    skipped_lines.extend(
        f"{entry.domain}|{entry.slug}|{entry.reason}|{entry.source_url or '-'}|{entry.manifest_path.as_posix()}"
        for entry in skipped
    )
    skipped_path.write_text("\n".join(skipped_lines) + "\n", encoding="utf-8")
    return output_path, skipped_path


def _print_summary(total_manifests: int, included: list[RepoEntry], skipped: list[SkippedEntry]) -> None:
    domain_counts = Counter(item.domain for item in included)
    skipped_counts = Counter(item.domain for item in skipped)
    print("S3M Vendor Manifest Build Summary")
    print("================================")
    print(f"Total manifests: {total_manifests}")
    print(f"Included: {len(included)}")
    print(f"Skipped: {len(skipped)}")
    print("Included by domain:")
    for domain in sorted(domain_counts):
        print(f"  - {domain}: {domain_counts[domain]}")
    print("Skipped by domain:")
    for domain in sorted(skipped_counts):
        print(f"  - {domain}: {skipped_counts[domain]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate scripts/vendor/repos.txt from integration manifests.")
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Destination path for repos manifest (default: scripts/vendor/repos.txt)",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    output_path = args.output.resolve()
    integrations_root = _project_root() / "packages" / "integrations"
    if not integrations_root.exists():
        raise FileNotFoundError(f"Integrations root not found: {integrations_root}")

    manifests = sorted(integrations_root.glob("*/*/manifest.yaml"))
    included, skipped = build_entries(integrations_root)
    repos_path, skipped_path = write_manifest_files(output_path, included, skipped)

    LOGGER.info("Wrote %d repo entries to %s", len(included), repos_path)
    LOGGER.info("Wrote %d skipped entries to %s", len(skipped), skipped_path)
    _print_summary(len(manifests), included, skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
