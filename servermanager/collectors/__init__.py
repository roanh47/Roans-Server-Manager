"""Data collectors: one module per source, no web imports anywhere in here."""

from __future__ import annotations

import psutil

from servermanager.config import Settings

from . import containers, ports, processes, services, system

__all__ = [
    "containers",
    "ports",
    "processes",
    "services",
    "system",
    "configure",
    "overview",
]


def configure(settings: Settings) -> None:
    """Point psutil at the host's /proc.

    Inside the container this is what makes the process, memory and disk views
    describe the server instead of the panel itself. Called once at startup.
    """
    psutil.PROCFS_PATH = settings.host_proc


def overview(settings: Settings) -> dict:
    """Everything the dashboard needs in one request.

    Each section reports its own failure rather than taking the page down with
    it: a missing Docker socket means the Docker panel is empty *and says why*.
    """
    return {
        "server": settings.server_name,
        "system": system.snapshot(settings),
        "processes": processes.snapshot(settings),
        "containers": containers.snapshot(settings),
        "ports": ports.snapshot(settings),
        "services": services.snapshot(settings),
    }
