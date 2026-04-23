"""Seccomp profile generation and process-level installation utilities."""

from __future__ import annotations

import ctypes
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_STRICT = 1


@dataclass(slots=True)
class SeccompProfile:
    """
    Builds OCI-compatible seccomp policies for agent process isolation.

    Tactical context:
    Seccomp is treated as the final containment layer when an adversarial agent
    bypasses userspace controls and attempts direct kernel abuse primitives.
    """

    mode: str = "strict"
    architectures: List[str] = field(
        default_factory=lambda: ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"]
    )
    _profile: Dict[str, object] | None = field(default=None, init=False, repr=False)

    def generate_profile(self, mode: str = "strict") -> Dict[str, object]:
        """Generate a seccomp profile dictionary for Docker/OCI runtimes."""
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"strict", "standard", "permissive"}:
            raise ValueError(f"Unsupported seccomp mode: {mode}")

        self.mode = normalized_mode
        blocked_syscalls = [
            "ptrace",
            "process_vm_readv",
            "process_vm_writev",
            "mount",
            "umount2",
            "setuid",
            "setgid",
            "setgroups",
            "personality",
            "unshare",
            "pivot_root",
            "chroot",
            "keyctl",
            "bpf",
            "perf_event_open",
            "userfaultfd",
            "kexec_load",
            "reboot",
            "init_module",
            "finit_module",
            "kcmp",
            "add_key",
            "request_key",
        ]
        required_allows = [
            "read",
            "write",
            "open",
            "openat",
            "close",
            "mmap",
            "mprotect",
            "brk",
            "clone",
            "fork",
            "vfork",
            "execve",
            "socket",
            "connect",
            "bind",
            "listen",
            "accept",
            "stat",
            "fstat",
            "lstat",
            "newfstatat",
            "getcwd",
            "chdir",
            "pipe",
            "pipe2",
            "dup",
            "dup2",
            "dup3",
            "epoll_create1",
            "epoll_ctl",
            "epoll_wait",
            "select",
            "pselect6",
            "poll",
            "ppoll",
            "futex",
            "clock_gettime",
            "rt_sigaction",
            "rt_sigprocmask",
            "exit",
            "exit_group",
            "sigreturn",
        ]

        standard_extras = [
            "access",
            "fcntl",
            "ioctl",
            "getpid",
            "gettid",
            "sched_yield",
            "nanosleep",
            "recvfrom",
            "sendto",
            "recvmsg",
            "sendmsg",
        ]
        permissive_extras = ["prctl", "madvise", "getrandom", "uname", "sysinfo"]

        allowed = list(required_allows)
        if normalized_mode in {"standard", "permissive"}:
            allowed.extend(standard_extras)
        if normalized_mode == "permissive":
            allowed.extend(permissive_extras)

        default_action = "SCMP_ACT_ERRNO"
        blocked_action = "SCMP_ACT_ERRNO"
        if normalized_mode == "permissive":
            default_action = "SCMP_ACT_ALLOW"
            blocked_action = "SCMP_ACT_LOG"

        self._profile = {
            "defaultAction": default_action,
            "architectures": list(self.architectures),
            "syscalls": [
                {"names": sorted(set(allowed)), "action": "SCMP_ACT_ALLOW"},
                {"names": blocked_syscalls, "action": blocked_action},
            ],
        }
        return dict(self._profile)

    def to_json(self) -> str:
        """Serialize the active seccomp profile to JSON."""
        if self._profile is None:
            self.generate_profile(mode=self.mode)
        return json.dumps(self._profile, indent=2, sort_keys=True)

    def install_for_process(self, pid: int) -> None:
        """
        Apply kernel seccomp controls to the current process using `prctl`.

        Tactical context:
        Process-local install avoids ptrace-based attachment, preserving
        anti-tamper guarantees in contested runtime environments.
        """
        if pid != os.getpid():
            raise PermissionError(
                "Seccomp install via prctl only supports the current process without privileged helpers."
            )

        libc = ctypes.CDLL(None, use_errno=True)

        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))

        # Strict mode activates kernel-enforced syscall minimization directly.
        if self.mode == "strict" and libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_STRICT, 0, 0, 0) != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
