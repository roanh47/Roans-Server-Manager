"""What is running, and how much of the machine it is taking.

Sorting is by CPU first, memory second, which is the order you actually want
when something is wrong. On a busy host a full sweep can be slow, so the caller
chooses the limit and the sweep is bounded.
"""

from __future__ import annotations

import psutil

from servermanager.config import Settings

from .services import resolve_owner


def _process_row(proc: psutil.Process) -> dict | None:
    try:
        with proc.oneshot():
            info = proc.as_dict(
                attrs=["pid", "name", "username", "cpu_percent", "memory_percent",
                       "memory_info", "cmdline", "exe", "status", "create_time"]
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    mem_info = info.get("memory_info")
    cmdline = info.get("cmdline") or []
    owner = resolve_owner(info["pid"])
    return {
        "pid": info["pid"],
        "name": info.get("name") or "?",
        "user": info.get("username") or "?",
        "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
        "memory_percent": round(info.get("memory_percent") or 0.0, 2),
        "rss_bytes": getattr(mem_info, "rss", 0) if mem_info else 0,
        "command": " ".join(cmdline) if cmdline else (info.get("exe") or info.get("name") or "?"),
        "status": info.get("status") or "?",
        "started_at": info.get("create_time") or 0.0,
        "owner_kind": owner["kind"],
        "owner": owner["name"],
    }


def snapshot(settings: Settings, limit: int = 40) -> dict:
    """The top ``limit`` processes by CPU, then memory."""
    # cpu_percent is a delta since the previous call, so prime it once: a process
    # created after that would otherwise report 0.0 on its first appearance.
    for proc in psutil.process_iter(["pid"]):
        try:
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    rows: list[dict] = []
    for proc in psutil.process_iter(["pid"]):
        row = _process_row(proc)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: (r["cpu_percent"], r["rss_bytes"]), reverse=True)
    total = len(rows)
    return {
        "count": total,
        "limit": limit,
        "processes": rows[:limit],
        "error": None,
    }
