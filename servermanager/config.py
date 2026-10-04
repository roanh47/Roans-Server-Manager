"""Configuration, read from the environment only.

Nothing here is baked into the image: docker-compose passes the environment in,
so changing how the panel behaves never needs a rebuild.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PORT = 8303
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    """Everything the panel reads from its environment."""

    server_name: str = "this server"
    # Bind address of the web UI. 127.0.0.1 only - see AGENTS.md.
    bind: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    # Shared secret. Empty means "the loopback bind is the only control".
    token: str = ""
    host_proc: str = "/proc"
    host_sys: str = "/sys"
    # The host's filesystem tree, mounted read-only. Empty or "/" means "this
    # container's own root", which is only correct outside Docker.
    host_root: str = ""
    docker_socket: str = "/var/run/docker.sock"
    web_dir: Path = field(default=PROJECT_DIR / "web")

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        src = os.environ if env is None else env
        raw_port = (src.get("SM_PORT") or str(DEFAULT_PORT)).strip()
        try:
            port = int(raw_port)
        except ValueError:
            port = DEFAULT_PORT
        return cls(
            server_name=(src.get("SM_SERVER_NAME") or "this server").strip(),
            bind=(src.get("SM_BIND") or "127.0.0.1").strip(),
            port=port,
            token=(src.get("SM_TOKEN") or "").strip(),
            host_proc=(src.get("SM_HOST_PROC") or "/proc").strip(),
            host_sys=(src.get("SM_HOST_SYS") or "/sys").strip(),
            host_root=(src.get("SM_HOST_ROOT") or "").strip(),
            docker_socket=(src.get("SM_DOCKER_SOCKET") or "/var/run/docker.sock").strip(),
        )

    @property
    def token_required(self) -> bool:
        return bool(self.token)
