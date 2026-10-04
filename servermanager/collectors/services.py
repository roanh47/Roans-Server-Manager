"""Which systemd unit (or container) a process belongs to.

Read straight from ``/proc/<pid>/cgroup``: the cgroup path names the unit, so a
process running outside Docker can be attributed to its service without D-Bus,
systemd bindings or a shelled-out ``systemctl``. That matters inside a container,
where none of those are available.

This is what makes the "other programs" view honest: the panel can tell a host
service apart from something running inside a container, instead of guessing.
"""

from __future__ import annotations

import re
from pathlib import Path

import psutil

from servermanager.config import Settings

KIND_SERVICE = "service"
KIND_CONTAINER = "container"
KIND_USER = "user"
KIND_UNMANAGED = "unmanaged"
KIND_UNKNOWN = "unknown"

_UNIT_RE = re.compile(r"(?P<unit>[A-Za-z0-9@:_.\\-]+\.service)")
_CONTAINER_MARKERS = ("/docker/", "docker-", "/containerd", "libpod", "/kubepods", "crio-")

_UNKNOWN_OWNER = {"kind": KIND_UNKNOWN, "name": "unknown"}


def parse_cgroup(text: str) -> dict:
    """Turn the contents of a cgroup file into an owner.

    ``0::/system.slice/ssh.service`` -> a service called ``ssh.service``.
    ``0::/system.slice/docker-abc123.scope`` -> a container.
    """
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return dict(_UNKNOWN_OWNER)

    lowered = cleaned.lower()
    if any(marker in lowered for marker in _CONTAINER_MARKERS):
        name = "container"
        for part in cleaned.replace("\\", "/").split("/"):
            if "docker-" in part or part.startswith("docker"):
                name = part.removesuffix(".scope")
                break
        return {"kind": KIND_CONTAINER, "name": name}

    match = _UNIT_RE.search(cleaned)
    if match:
        return {"kind": KIND_SERVICE, "name": match.group("unit")}

    if "user.slice" in lowered or "/user@" in lowered:
        return {"kind": KIND_USER, "name": "user session"}

    return {"kind": KIND_UNMANAGED, "name": "unmanaged"}


def read_cgroup(pid: int, proc_root: str | None = None) -> str | None:
    root = Path(proc_root or psutil.PROCFS_PATH)
    try:
        return (root / str(pid) / "cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def resolve_owner(pid: int, proc_root: str | None = None) -> dict:
    """Owner of one pid, never raising: an unreadable cgroup is 'unknown'."""
    text = read_cgroup(pid, proc_root)
    if text is None:
        return dict(_UNKNOWN_OWNER)
    return parse_cgroup(text)


def _empty(reason: str | None = None) -> dict:
    return {"units": [], "count": 0, "error": reason}


def snapshot(settings: Settings, limit: int = 60) -> dict:
    """Host programs grouped by systemd unit, containers excluded."""
    groups: dict[str, dict] = {}
    container_processes = 0
    unreadable = 0

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = proc.pid
            name = proc.info.get("name") or "?"
            owner = resolve_owner(pid, settings.host_proc)
            if owner["kind"] == KIND_CONTAINER:
                container_processes += 1
                continue
            if owner["kind"] == KIND_UNKNOWN:
                unreadable += 1
                continue

            try:
                with proc.oneshot():
                    cpu = proc.cpu_percent(interval=None)
                    rss = proc.memory_info().rss
                    username = proc.username()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                cpu, rss, username = 0.0, 0, "?"

            key = owner["name"]
            entry = groups.setdefault(
                key,
                {
                    "name": key,
                    "kind": owner["kind"],
                    "pids": [],
                    "process_count": 0,
                    "cpu_percent": 0.0,
                    "rss_bytes": 0,
                    "user": username,
                    "main_process": name,
                },
            )
            entry["pids"].append(pid)
            entry["process_count"] += 1
            entry["cpu_percent"] += cpu or 0.0
            entry["rss_bytes"] += rss or 0
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    units = []
    for entry in groups.values():
        entry["cpu_percent"] = round(entry["cpu_percent"], 1)
        entry["pids"] = sorted(entry["pids"])[:12]
        units.append(entry)
    units.sort(key=lambda u: (u["kind"] != KIND_SERVICE, -u["rss_bytes"]))

    return {
        "units": units[:limit],
        "count": len(units),
        "container_processes": container_processes,
        "unreadable_processes": unreadable,
        "error": None,
    }
