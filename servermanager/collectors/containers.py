"""Docker containers, from the socket.

Nothing is started or stopped here: this module only reports. The Docker socket
is mounted read-only in spirit (it cannot actually be mounted read-only), which
is why the API surface stays read-only and the panel binds to loopback.
"""

from __future__ import annotations

from typing import Any

from servermanager.config import Settings


def _client(socket_path: str) -> Any:
    import docker  # imported lazily so the tests can run without the package

    return docker.DockerClient(base_url=f"unix://{socket_path}", timeout=6)


def _container_row(container: Any) -> dict:
    attrs = container.attrs or {}
    state = (attrs.get("State") or {}).get("Status") or container.status
    health = ((attrs.get("State") or {}).get("Health") or {}).get("Status")
    network = attrs.get("NetworkSettings") or {}
    ports = network.get("Ports") or {}
    published = []
    for container_port, bindings in ports.items():
        if not bindings:
            published.append({"container_port": container_port, "host_ip": None, "host_port": None})
            continue
        for binding in bindings:
            published.append(
                {
                    "container_port": container_port,
                    "host_ip": binding.get("HostIp"),
                    "host_port": binding.get("HostPort"),
                }
            )
    labels = attrs.get("Config", {}).get("Labels") or {}
    return {
        "id": container.short_id,
        "name": container.name,
        "image": (attrs.get("Config") or {}).get("Image") or container.image.tags[:1],
        "state": state,
        "running": bool((attrs.get("State") or {}).get("Running")),
        "health": health,
        "created": attrs.get("Created"),
        "started_at": (attrs.get("State") or {}).get("StartedAt"),
        "restart_count": attrs.get("RestartCount", 0),
        "ports": published,
        # 0.0.0.0 on a published port is a real exposure and belongs in the UI.
        "exposes_all_interfaces": any(
            p["host_ip"] in ("0.0.0.0", "::") for p in published if p["host_ip"]
        ),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
    }


def snapshot(settings: Settings) -> dict:
    try:
        client = _client(settings.docker_socket)
        containers = client.containers.list(all=True)
    except Exception as exc:  # docker.errors.* and connection failures alike
        return {
            "containers": [],
            "count": 0,
            "running": 0,
            "unhealthy": 0,
            "error": f"docker socket unavailable: {type(exc).__name__}: {exc}",
        }

    rows = [_container_row(c) for c in containers]
    rows.sort(key=lambda r: (not r["running"], r["name"]))
    return {
        "containers": rows,
        "count": len(rows),
        "running": sum(1 for r in rows if r["running"]),
        "unhealthy": sum(1 for r in rows if r["health"] == "unhealthy"),
        "exposed": sum(1 for r in rows if r["exposes_all_interfaces"]),
        "error": None,
    }
