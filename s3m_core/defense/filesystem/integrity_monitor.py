"""Real-time filesystem integrity monitoring with cryptographic baselining."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
import difflib
import hashlib
import os
from pathlib import Path
import struct
import threading
import time
from typing import Callable, Dict, List, Literal

SeverityLevel = Literal["routine", "suspicious", "critical"]


@dataclass(frozen=True)
class FileChangeEvent:
    """Single file-change record used for forensic timeline reconstruction."""

    timestamp: str
    path: str
    event_type: str
    old_hash: str | None
    new_hash: str | None
    changed_by_pid: int
    changed_by_binary: str
    diff_summary: str
    severity: SeverityLevel


@dataclass(frozen=True)
class IntegrityReport:
    """Hash comparison report that indicates whether monitored assets drifted."""

    total_files: int
    files_checked: int
    modified: List[str]
    added: List[str]
    deleted: List[str]
    tampered: bool


class FilesystemIntegrityMonitor:
    """
    Monitor mission files in real time and flag covert tampering attempts.

    Tactical context:
    Rapid, cryptographic drift detection prevents adversarial agents from
    changing files between safety checks during high-tempo operations.
    """

    IN_CREATE = 0x00000100
    IN_MODIFY = 0x00000002
    IN_DELETE = 0x00000200
    IN_MOVED_FROM = 0x00000040
    IN_MOVED_TO = 0x00000080
    IN_ATTRIB = 0x00000004
    IN_ISDIR = 0x40000000
    _EVENT_MASK = IN_CREATE | IN_MODIFY | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO | IN_ATTRIB

    _SUSPICIOUS_NAMES = {
        ".env",
        ".gitignore",
        ".gitattributes",
        ".bashrc",
        ".zshrc",
        ".profile",
        "config.yaml",
        "config.yml",
        "config.ini",
    }
    _CRITICAL_PREFIXES = ("/etc/", "/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/lib/", "/lib64/")
    _CREDENTIAL_FILE_MARKERS = (
        "id_rsa",
        "id_ed25519",
        "authorized_keys",
        "credentials",
        "kubeconfig",
        "token",
        "secret",
    )

    def __init__(
        self,
        watch_paths: List[str],
        hash_algorithm: str = "sha256",
        alert_callback: Callable[[FileChangeEvent], None] | None = None,
    ) -> None:
        if not watch_paths:
            raise ValueError("watch_paths must contain at least one path")
        if hash_algorithm not in hashlib.algorithms_available:
            raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}")
        if alert_callback is not None and not callable(alert_callback):
            raise TypeError("alert_callback must be callable")

        self.watch_paths = [os.path.abspath(path) for path in watch_paths]
        self.hash_algorithm = hash_algorithm
        self.alert_callback = alert_callback

        self._baseline_by_root: dict[str, dict[str, str]] = {}
        self._content_preview_by_root: dict[str, dict[str, str]] = {}
        self._change_log: list[FileChangeEvent] = []

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._fd_to_path: dict[int, str] = {}
        self._inotify_fd: int | None = None
        self._libc: ctypes.CDLL | None = None

    def baseline(self, path: str) -> Dict[str, str]:
        """Walk a directory tree and store cryptographic hashes for every file."""
        root = os.path.abspath(path)
        if not os.path.isdir(root):
            raise ValueError(f"baseline path must be an existing directory: {path}")

        baseline_map, preview_map = self._walk_and_hash(root)
        with self._lock:
            self._baseline_by_root[root] = baseline_map
            self._content_preview_by_root[root] = preview_map
        return baseline_map.copy()

    def start_monitoring(self) -> None:
        """Begin inotify-backed monitoring in a dedicated daemon thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        for path in self.watch_paths:
            if os.path.isdir(path) and path not in self._baseline_by_root:
                self.baseline(path)

        self._initialize_inotify()
        self._register_recursive_watches()
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring and release kernel watch descriptors."""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        if self._inotify_fd is not None:
            try:
                os.close(self._inotify_fd)
            except OSError:
                pass
            self._inotify_fd = None
        self._fd_to_path.clear()

    def verify_integrity(self, path: str | None = None) -> IntegrityReport:
        """Re-hash monitored files and compare against baseline snapshots."""
        if path is None:
            target_roots = list(self._baseline_by_root)
        else:
            safe_path = os.path.abspath(path)
            target_roots = [root for root in self._baseline_by_root if self._is_within(root, safe_path)]
            if not target_roots and os.path.isdir(safe_path):
                target_roots = [safe_path]

        modified: list[str] = []
        added: list[str] = []
        deleted: list[str] = []
        total_files = 0
        files_checked = 0

        for root in target_roots:
            current_hashes, _ = self._walk_and_hash(root)
            baseline_hashes = self._baseline_by_root.get(root, {})
            total_files += len(baseline_hashes)
            files_checked += len(current_hashes)

            all_keys = sorted(set(baseline_hashes) | set(current_hashes))
            for rel_path in all_keys:
                baseline_hash = baseline_hashes.get(rel_path)
                current_hash = current_hashes.get(rel_path)
                joined = os.path.join(root, rel_path)
                if baseline_hash is None and current_hash is not None:
                    added.append(joined)
                elif baseline_hash is not None and current_hash is None:
                    deleted.append(joined)
                elif baseline_hash != current_hash:
                    modified.append(joined)

        tampered = bool(modified or added or deleted)
        return IntegrityReport(
            total_files=total_files,
            files_checked=files_checked,
            modified=modified,
            added=added,
            deleted=deleted,
            tampered=tampered,
        )

    def get_change_log(self) -> List[FileChangeEvent]:
        """Return ordered forensic timeline of file events seen so far."""
        with self._lock:
            return list(self._change_log)

    def _initialize_inotify(self) -> None:
        if os.name != "posix":
            raise RuntimeError("FilesystemIntegrityMonitor requires Linux inotify support")
        self._libc = ctypes.CDLL("libc.so.6", use_errno=True)
        init = self._libc.inotify_init1
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int

        fd = init(os.O_NONBLOCK)
        if fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        self._inotify_fd = fd

    def _register_recursive_watches(self) -> None:
        if self._inotify_fd is None or self._libc is None:
            return
        add_watch = self._libc.inotify_add_watch
        add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        add_watch.restype = ctypes.c_int

        for root in self.watch_paths:
            if not os.path.isdir(root):
                continue
            for dir_path, _, _ in os.walk(root):
                wd = add_watch(self._inotify_fd, dir_path.encode("utf-8"), self._EVENT_MASK)
                if wd >= 0:
                    self._fd_to_path[wd] = dir_path

    def _monitor_loop(self) -> None:
        event_header = struct.Struct("iIII")
        while not self._stop_event.is_set():
            if self._inotify_fd is None:
                break
            try:
                raw = os.read(self._inotify_fd, 65536)
            except BlockingIOError:
                time.sleep(0.20)
                continue
            except OSError:
                break

            cursor = 0
            while cursor + event_header.size <= len(raw):
                wd, mask, _cookie, name_len = event_header.unpack_from(raw, cursor)
                cursor += event_header.size
                raw_name = raw[cursor : cursor + name_len]
                cursor += name_len
                name = raw_name.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
                directory = self._fd_to_path.get(wd, "")
                full_path = os.path.join(directory, name) if name else directory
                if not full_path:
                    continue

                if (mask & self.IN_ISDIR) and (mask & (self.IN_CREATE | self.IN_MOVED_TO)):
                    self._register_new_directory(full_path)

                event_type = self._event_name(mask)
                self._record_event(full_path, event_type)

    def _register_new_directory(self, directory: str) -> None:
        if self._inotify_fd is None or self._libc is None or not os.path.isdir(directory):
            return
        add_watch = self._libc.inotify_add_watch
        wd = add_watch(self._inotify_fd, directory.encode("utf-8"), self._EVENT_MASK)
        if wd >= 0:
            self._fd_to_path[wd] = directory
        for dir_path, _, _ in os.walk(directory):
            wd = add_watch(self._inotify_fd, dir_path.encode("utf-8"), self._EVENT_MASK)
            if wd >= 0:
                self._fd_to_path[wd] = dir_path

    def _record_event(self, full_path: str, event_type: str) -> None:
        root = self._match_root(full_path)
        if root is None:
            return
        relative = os.path.relpath(full_path, root)
        baseline_map = self._baseline_by_root.setdefault(root, {})
        preview_map = self._content_preview_by_root.setdefault(root, {})

        old_hash = baseline_map.get(relative)
        old_preview = preview_map.get(relative, "")
        new_hash: str | None = None
        new_preview = ""

        if os.path.isfile(full_path):
            new_hash = self._hash_file(full_path)
            new_preview = self._read_preview(full_path)
            baseline_map[relative] = new_hash
            preview_map[relative] = new_preview
        elif event_type in {"delete", "moved_from"}:
            baseline_map.pop(relative, None)
            preview_map.pop(relative, None)

        diff_summary = self._diff_summary(old_preview, new_preview)
        changed_by_pid, changed_by_binary = self._identify_actor(full_path)
        severity = self._classify_severity(full_path)

        event = FileChangeEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            path=full_path,
            event_type=event_type,
            old_hash=old_hash,
            new_hash=new_hash,
            changed_by_pid=changed_by_pid,
            changed_by_binary=changed_by_binary,
            diff_summary=diff_summary,
            severity=severity,
        )
        with self._lock:
            self._change_log.append(event)

        if self.alert_callback is not None:
            try:
                self.alert_callback(event)
            except Exception:
                # Monitoring must continue even if callback handlers fail.
                pass

    @staticmethod
    def _event_name(mask: int) -> str:
        if mask & FilesystemIntegrityMonitor.IN_DELETE:
            return "delete"
        if mask & FilesystemIntegrityMonitor.IN_MOVED_FROM:
            return "moved_from"
        if mask & FilesystemIntegrityMonitor.IN_MOVED_TO:
            return "moved_to"
        if mask & FilesystemIntegrityMonitor.IN_CREATE:
            return "create"
        if mask & FilesystemIntegrityMonitor.IN_MODIFY:
            return "modify"
        if mask & FilesystemIntegrityMonitor.IN_ATTRIB:
            return "attrib"
        return "unknown"

    def _walk_and_hash(self, root: str) -> tuple[dict[str, str], dict[str, str]]:
        hashed: dict[str, str] = {}
        previews: dict[str, str] = {}
        for dir_path, _, files in os.walk(root):
            for file_name in files:
                file_path = os.path.join(dir_path, file_name)
                if not os.path.isfile(file_path):
                    continue
                rel_path = os.path.relpath(file_path, root)
                hashed[rel_path] = self._hash_file(file_path)
                previews[rel_path] = self._read_preview(file_path)
        return hashed, previews

    def _hash_file(self, file_path: str) -> str:
        hasher = hashlib.new(self.hash_algorithm)
        with open(file_path, "rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _read_preview(file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read(4096)
        except OSError:
            return ""

    @staticmethod
    def _diff_summary(old_content: str, new_content: str) -> str:
        if old_content == new_content:
            return ""
        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
        return "\n".join(diff)[:500]

    def _classify_severity(self, full_path: str) -> SeverityLevel:
        normalized = os.path.abspath(full_path)
        lower = normalized.lower()
        base_name = os.path.basename(lower)

        if "/.git/" in lower or lower.endswith("/.git"):
            return "critical"
        if normalized.startswith(self._CRITICAL_PREFIXES):
            return "critical"
        if any(marker in base_name for marker in self._CREDENTIAL_FILE_MARKERS):
            return "critical"
        if base_name in self._SUSPICIOUS_NAMES:
            return "suspicious"
        if base_name.startswith("."):
            return "suspicious"
        if any(part in {"config", "configs"} for part in Path(lower).parts):
            return "suspicious"
        return "routine"

    def _identify_actor(self, full_path: str) -> tuple[int, str]:
        real_target = os.path.realpath(full_path)
        try:
            proc_entries = list(os.scandir("/proc"))
        except OSError:
            return -1, "unknown"

        for proc_entry in proc_entries:
            if not proc_entry.name.isdigit():
                continue
            pid = int(proc_entry.name)
            fd_dir = os.path.join("/proc", proc_entry.name, "fd")
            exe_link = os.path.join("/proc", proc_entry.name, "exe")
            try:
                for fd_entry in os.scandir(fd_dir):
                    try:
                        target = os.path.realpath(os.readlink(fd_entry.path))
                    except OSError:
                        continue
                    if target == real_target:
                        binary = "unknown"
                        try:
                            binary = os.path.basename(os.readlink(exe_link))
                        except OSError:
                            pass
                        return pid, binary
            except OSError:
                continue
        return -1, "unknown"

    def _match_root(self, full_path: str) -> str | None:
        normalized = os.path.abspath(full_path)
        candidates = [root for root in self._baseline_by_root if self._is_within(root, normalized)]
        if not candidates:
            return None
        return max(candidates, key=len)

    @staticmethod
    def _is_within(root: str, path: str) -> bool:
        root_abs = os.path.abspath(root)
        path_abs = os.path.abspath(path)
        try:
            return os.path.commonpath([root_abs, path_abs]) == root_abs
        except ValueError:
            return False
