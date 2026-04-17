"""Sandbox configuration primitives for hardened agent isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(slots=True)
class SandboxConfig:
    """
    Defines the process and filesystem isolation boundary for one agent session.

    Tactical context:
    This boundary is tuned to stop credential theft via `/proc` introspection,
    matching known adversary tradecraft used against multi-agent runtimes.
    """

    # Namespace isolation
    use_pid_namespace: bool = True
    use_net_namespace: bool = True
    use_mount_namespace: bool = True
    use_user_namespace: bool = True

    # /proc hardening (priority defense line)
    mount_proc_readonly: bool = True
    hide_other_pids: bool = True
    mask_proc_paths: List[str] = field(
        default_factory=lambda: [
            "/proc/*/environ",
            "/proc/*/mem",
            "/proc/*/maps",
            "/proc/*/fd",
            "/proc/*/cmdline",
            "/proc/*/status",
            "/proc/kcore",
            "/proc/sysrq-trigger",
            "/proc/*/root",
        ]
    )

    # Ptrace protection
    disable_ptrace: bool = True

    # Device access
    allowed_devices: List[str] = field(
        default_factory=lambda: [
            "/dev/null",
            "/dev/zero",
            "/dev/urandom",
        ]
    )

    # Resource limits
    max_memory_mb: int = 4096
    max_cpu_percent: int = 80
    max_open_files: int = 1024
    max_processes: int = 64
    max_file_size_mb: int = 512

    # Runtime controls
    runtime: str = "gvisor"

    def to_docker_args(self) -> List[str]:
        """Convert this isolation policy into `docker run` arguments."""
        args: List[str] = [
            "--cap-drop=ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.max_processes),
            "--memory",
            f"{self.max_memory_mb}m",
            "--cpus",
            f"{self.max_cpu_percent / 100:.2f}",
            "--ulimit",
            f"nofile={self.max_open_files}:{self.max_open_files}",
            "--ulimit",
            f"fsize={self.max_file_size_mb * 1024}",
            "--label",
            f"s3m.masked_proc_paths={','.join(self.mask_proc_paths)}",
        ]

        args.extend(["--pid=private" if self.use_pid_namespace else "--pid=host"])
        args.extend(["--network=bridge" if self.use_net_namespace else "--network=host"])
        args.extend(["--userns=private" if self.use_user_namespace else "--userns=host"])

        if self.use_mount_namespace:
            args.append("--read-only")
        if self.mount_proc_readonly:
            args.extend(["--mount", "type=bind,src=/proc,dst=/proc,readonly"])
        if self.hide_other_pids:
            # Tactical note: hidepid cannot always be applied directly by Docker,
            # so this flag is surfaced as intent for the runtime orchestrator.
            args.extend(["--security-opt", "s3m.procfs-hidepid=2"])
        if self.disable_ptrace:
            args.extend(["--security-opt", "s3m.disable-ptrace=true"])
            args.extend(["--cap-drop=SYS_PTRACE"])

        for device in self.allowed_devices:
            args.extend(["--device", f"{device}:{device}:r"])
        return args

    def to_gvisor_config(self) -> Dict[str, object]:
        """Convert policy into a `runsc`-compatible settings dictionary."""
        return {
            "runtime": "runsc",
            "platform": "systrap",
            "rootless": self.use_user_namespace,
            "network": "sandbox" if self.use_net_namespace else "host",
            "readonly_rootfs": self.use_mount_namespace and self.mount_proc_readonly,
            "procfs": {
                "readonly": self.mount_proc_readonly,
                "hidepid": 2 if self.hide_other_pids else 0,
                "masked_paths": list(self.mask_proc_paths),
            },
            "security": {
                "disable_ptrace": self.disable_ptrace,
                "allowed_devices": list(self.allowed_devices),
            },
            "limits": {
                "memory_mb": self.max_memory_mb,
                "cpu_percent": self.max_cpu_percent,
                "open_files": self.max_open_files,
                "processes": self.max_processes,
                "file_size_mb": self.max_file_size_mb,
            },
        }

    def validate(self) -> List[str]:
        """Return warnings for known hardening gaps in this sandbox policy."""
        warnings: List[str] = []
        valid_runtimes = {"gvisor", "firecracker", "docker"}
        dangerous_devices = {"/dev/mem", "/dev/kmem", "/dev/port"}
        required_proc_masks = {"/proc/*/environ", "/proc/*/mem", "/proc/*/fd"}

        if self.runtime not in valid_runtimes:
            warnings.append(f"Unsupported runtime '{self.runtime}' configured.")
        if self.runtime == "docker":
            warnings.append("Docker runtime provides minimum viable isolation for frontier agents.")

        if not self.use_pid_namespace:
            warnings.append("PID namespace is disabled: agent can enumerate host processes.")
        if not self.use_net_namespace:
            warnings.append("Network namespace is disabled: lateral movement risk increases.")
        if not self.use_mount_namespace:
            warnings.append("Mount namespace is disabled: host filesystem exposure risk.")
        if not self.use_user_namespace:
            warnings.append("User namespace is disabled: privilege boundaries are weakened.")

        if not self.mount_proc_readonly:
            warnings.append("/proc is writable: kernel and process metadata can be tampered with.")
        if not self.hide_other_pids:
            warnings.append("hidepid protection disabled: cross-process reconnaissance risk.")
        if not self.disable_ptrace:
            warnings.append("Ptrace is enabled: debugger-assisted memory scraping risk.")

        missing_masks = required_proc_masks.difference(self.mask_proc_paths)
        if missing_masks:
            warnings.append(
                "Critical /proc mask entries missing: " + ", ".join(sorted(missing_masks))
            )

        present_dangerous_devices = sorted(dangerous_devices.intersection(self.allowed_devices))
        if present_dangerous_devices:
            warnings.append(
                "Dangerous device nodes exposed: " + ", ".join(present_dangerous_devices)
            )

        if self.max_memory_mb <= 0:
            warnings.append("Memory limit must be greater than zero.")
        if self.max_cpu_percent <= 0 or self.max_cpu_percent > 100:
            warnings.append("CPU limit should be between 1 and 100 percent.")
        if self.max_open_files <= 0:
            warnings.append("Open file descriptor limit must be greater than zero.")
        if self.max_processes <= 0:
            warnings.append("Process count limit must be greater than zero.")
        if self.max_file_size_mb <= 0:
            warnings.append("Maximum file size limit must be greater than zero.")
        return warnings
