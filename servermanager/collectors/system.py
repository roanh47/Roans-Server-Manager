"""What this machine is and how hard it is working.

Uses psutil, which reads /proc - pointed at the *host's* /proc by
``collectors.configure()``. Anything that cannot be read comes back as an
explicit error instead of a plausible-looking zero.
"""

from __future__ import annotations

import platform
import shutil
import time
from pathlib import Path

import psutil

from servermanager.config import Settings

# Boot time is picked up once; psutil.boot_time() reads /proc/stat every call.
_BOOT_TIME = psutil.boot_time()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _cpu_model(host_proc: str) -> str | None:
    text = _read_text(Path(host_proc) / "cpuinfo")
    if not text:
        return None
    for line in text.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return None


def _uptime_seconds() -> float:
    return max(0.0, time.time() - _BOOT_TIME)


_PSEUDO_FILESYSTEMS = {
    "autofs", "binfmt_misc", "bpf", "cgroup", "cgroup2", "configfs", "debugfs",
    "devpts", "devtmpfs", "efivarfs", "fusectl", "hugetlbfs", "mqueue", "nsfs",
    "overlay", "proc", "pstore", "ramfs", "rpc_pipefs", "securityfs",
    "squashfs", "sysfs", "tmpfs", "tracefs",
}


def parse_mounts(text: str) -> list[dict]:
    """Real filesystems from a mount table, one entry per device.

    A device mounted in several places (bind mounts, chroots) is reported once,
    at its shortest mount point: that is the one a human means by "the disk".
    """
    best: dict[str, dict] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount, fstype = parts[0], parts[1].replace("\\040", " "), parts[2]
        if fstype in _PSEUDO_FILESYSTEMS or not device.startswith("/"):
            continue
        current = best.get(device)
        if current is None or len(mount) < len(current["mount"]):
            best[device] = {"device": device, "mount": mount, "fstype": fstype}
    return sorted(best.values(), key=lambda entry: entry["mount"])


def _disks(settings: Settings) -> list[dict]:
    """Disks of the *host*, not of this container.

    Sizes must be read from the host's mount table: inside a container,
    /proc/mounts lists the container's own bind mounts, and "/" is an overlay
    whose numbers have nothing to do with the disk the server stores things on.
    """
    proc_root = Path(settings.host_proc)
    for candidate in (proc_root / "1" / "mounts", proc_root / "mounts"):
        try:
            text = candidate.read_text()
        except OSError:
            continue
        if text.strip():
            break
    else:
        return []

    root = settings.host_root.rstrip("/")
    out: list[dict] = []
    for entry in parse_mounts(text):
        path = f"{root}{entry['mount']}" if root else entry["mount"]
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        if usage.total <= 0:
            continue
        out.append(
            {
                "mount": entry["mount"],
                "device": entry["device"],
                "fstype": entry["fstype"],
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "percent": round(usage.used / usage.total * 100, 1),
            }
        )
    out.sort(key=lambda disk: disk["total_bytes"], reverse=True)
    return out


def snapshot(settings: Settings) -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    load1, load5, load15 = psutil.getloadavg()
    boot = _BOOT_TIME
    return {
        "hostname": platform.node(),
        "server_name": settings.server_name,
        "os": f"{platform.system()} {platform.release()}",
        "kernel": platform.release(),
        "arch": platform.machine(),
        "cpu_model": _cpu_model(settings.host_proc) or platform.processor() or "unknown",
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_percent": round(cpu_percent, 1),
        "load": {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)},
        "memory": {
            "total_bytes": memory.total,
            "used_bytes": memory.total - memory.available,
            "available_bytes": memory.available,
            "percent": round(memory.percent, 1),
        },
        "swap": {
            "total_bytes": swap.total,
            "used_bytes": swap.used,
            "percent": round(swap.percent, 1),
        },
        "disks": _disks(settings),
        "boot_time": boot,
        "uptime_seconds": round(_uptime_seconds()),
        "process_count": len(psutil.pids()),
        "error": None,
    }
