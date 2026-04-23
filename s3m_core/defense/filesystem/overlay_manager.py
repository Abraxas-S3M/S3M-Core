"""OverlayFS session manager for immutable-base forensic auditing."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import List


@dataclass(frozen=True)
class OverlayMount:
    """Metadata describing one active overlay mount session."""

    session_id: str
    base_path: str
    upper_path: str
    merged_path: str


@dataclass(frozen=True)
class FileChange:
    """Change item recovered from overlay upperdir after a mission run."""

    path: str
    change_type: str
    content_preview: str
    size_bytes: int


class OverlayFSManager:
    """
    Keep the mission base tree immutable while agents write to an overlay.

    Tactical context:
    Immutable lower layers guarantee post-operation forensics can reconstruct
    every write attempt without trusting the agent that performed the action.
    """

    def __init__(self, base_path: str, work_dir: str = "/tmp/s3m_overlay") -> None:
        safe_base = os.path.abspath(base_path)
        if not os.path.isdir(safe_base):
            raise ValueError(f"base_path must be an existing directory: {base_path}")
        self.base_path = safe_base
        self.work_dir = os.path.abspath(work_dir)
        self._sessions: dict[str, dict[str, object]] = {}

    def create_overlay(self, session_id: str) -> OverlayMount:
        """Create and mount OverlayFS directories for one agent session."""
        safe_session = self._validate_session_id(session_id)
        session_root = os.path.join(self.work_dir, safe_session)
        upper = os.path.join(session_root, "upper")
        work = os.path.join(session_root, "work")
        merged = os.path.join(session_root, "merged")

        os.makedirs(upper, exist_ok=True)
        os.makedirs(work, exist_ok=True)
        os.makedirs(merged, exist_ok=True)

        command = [
            "mount",
            "-t",
            "overlay",
            "overlay",
            "-o",
            f"lowerdir={self.base_path},upperdir={upper},workdir={work}",
            merged,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"Overlay mount failed: {completed.stderr.strip()}")

        mount = OverlayMount(
            session_id=safe_session,
            base_path=self.base_path,
            upper_path=upper,
            merged_path=merged,
        )
        self._sessions[safe_session] = {
            "mount": mount,
            "session_root": session_root,
            "base_hashes": self._snapshot_hashes(self.base_path),
        }
        return mount

    def get_changes(self, session_id: str) -> List[FileChange]:
        """Return a complete file change inventory from overlay upperdir."""
        session = self._get_session(session_id)
        mount: OverlayMount = session["mount"]  # type: ignore[assignment]
        base_hashes: dict[str, str] = session["base_hashes"]  # type: ignore[assignment]
        changes: list[FileChange] = []

        for dir_path, _, files in os.walk(mount.upper_path):
            rel_dir = os.path.relpath(dir_path, mount.upper_path)
            rel_dir = "" if rel_dir == "." else rel_dir
            for file_name in files:
                overlay_path = os.path.join(dir_path, file_name)
                if file_name == ".wh..wh..opq":
                    deleted_dir = rel_dir
                    changes.append(
                        FileChange(
                            path=deleted_dir,
                            change_type="deleted",
                            content_preview="",
                            size_bytes=0,
                        )
                    )
                    continue
                if file_name.startswith(".wh."):
                    deleted_rel = os.path.normpath(os.path.join(rel_dir, file_name[4:]))
                    changes.append(
                        FileChange(
                            path=deleted_rel,
                            change_type="deleted",
                            content_preview="",
                            size_bytes=0,
                        )
                    )
                    continue

                rel_path = os.path.normpath(os.path.join(rel_dir, file_name))
                file_hash = self._hash_file(overlay_path)
                if rel_path in base_hashes and base_hashes[rel_path] != file_hash:
                    change_type = "modified"
                elif rel_path in base_hashes:
                    # OverlayFS stores copied-up files even without content changes.
                    change_type = "modified"
                else:
                    change_type = "created"

                size_bytes = os.path.getsize(overlay_path)
                changes.append(
                    FileChange(
                        path=rel_path,
                        change_type=change_type,
                        content_preview=self._read_preview(overlay_path),
                        size_bytes=size_bytes,
                    )
                )

        return sorted(changes, key=lambda item: (item.path, item.change_type))

    def commit_changes(self, session_id: str, approved_paths: List[str]) -> None:
        """Copy only approved overlay changes into the immutable base tree."""
        session = self._get_session(session_id)
        mount: OverlayMount = session["mount"]  # type: ignore[assignment]
        approved = {self._normalize_relative(path) for path in approved_paths}
        for change in self.get_changes(session_id):
            rel_path = self._normalize_relative(change.path)
            if rel_path not in approved:
                continue

            target = os.path.join(self.base_path, rel_path)
            if change.change_type == "deleted":
                if os.path.isfile(target):
                    os.remove(target)
                elif os.path.isdir(target):
                    shutil.rmtree(target)
                continue

            source = os.path.join(mount.upper_path, rel_path)
            if not os.path.isfile(source):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)

    def discard(self, session_id: str) -> None:
        """Unmount and delete session overlay directories."""
        safe_session = self._validate_session_id(session_id)
        session = self._sessions.get(safe_session)
        if session is None:
            return
        mount: OverlayMount = session["mount"]  # type: ignore[assignment]
        session_root: str = session["session_root"]  # type: ignore[assignment]

        subprocess.run(["umount", mount.merged_path], capture_output=True, text=True)
        shutil.rmtree(session_root, ignore_errors=True)
        self._sessions.pop(safe_session, None)

    def _get_session(self, session_id: str) -> dict[str, object]:
        safe_session = self._validate_session_id(session_id)
        session = self._sessions.get(safe_session)
        if session is None:
            raise KeyError(f"Unknown overlay session: {session_id}")
        return session

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        safe = str(session_id).strip()
        if not safe:
            raise ValueError("session_id must be non-empty")
        if any(char in safe for char in ("/", "\\", "..")):
            raise ValueError("session_id must not contain path traversal characters")
        return safe

    @staticmethod
    def _normalize_relative(path: str) -> str:
        rel = os.path.normpath(path.strip())
        if rel.startswith("../") or rel == ".." or os.path.isabs(rel):
            raise ValueError(f"approved path must be relative to base tree: {path}")
        return rel

    @staticmethod
    def _read_preview(file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read(500)
        except OSError:
            return ""

    @staticmethod
    def _hash_file(file_path: str) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _snapshot_hashes(self, root: str) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for dir_path, _, files in os.walk(root):
            for file_name in files:
                full = os.path.join(dir_path, file_name)
                if not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, root)
                snapshot[Path(rel).as_posix()] = self._hash_file(full)
        return snapshot
