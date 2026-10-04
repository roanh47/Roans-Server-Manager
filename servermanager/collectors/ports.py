"""Every listening port, and what it is actually reachable from.

The interesting question is never "which port is open" but "which port is open
to the world", and the kernel already knows the answer: the bind address. A
socket on ``127.0.0.1`` is unreachable from the LAN no matter what the firewall
says; a socket on ``0.0.0.0`` answers on every interface the machine has.

Two independent sources are merged on purpose:

- ``/proc/net/tcp`` (and tcp6/udp/udp6) is authoritative for the bind address,
  port and socket inode, and works without any privilege;
- a walk over ``/proc/<pid>/fd`` turns that inode into a pid, which is then
  resolved to a systemd unit or a container via ``/proc/<pid>/cgroup``.
  ``psutil.net_connections()`` is the fallback for sockets the fd walk could not
  reach.

If attribution fails the row still appears, with an explicit ``unknown`` owner -
a port list missing its owners is still a useful port list, a port list hiding
rows is not.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

import psutil

from servermanager.config import Settings

from .services import KIND_CONTAINER, KIND_SERVICE, KIND_USER, resolve_owner

SCOPE_LOCALHOST = "localhost"
SCOPE_TAILSCALE = "tailscale"
SCOPE_LAN = "lan"
SCOPE_CONTAINER = "container"
SCOPE_LINK_LOCAL = "link-local"
SCOPE_PUBLIC = "public"
SCOPE_OTHER = "other"

# Tailscale hands out 100.64.0.0/10 (RFC 6598 carrier-grade NAT space).
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
CONTAINER_NETS = (
    ipaddress.ip_network("172.17.0.0/16"),  # docker default bridge
    ipaddress.ip_network("172.18.0.0/16"),
    ipaddress.ip_network("172.19.0.0/16"),
    ipaddress.ip_network("172.20.0.0/14"),
    ipaddress.ip_network("172.24.0.0/13"),
    ipaddress.ip_network("10.88.0.0/16"),  # podman
)
LAN_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
LINK_LOCAL_NETS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)

_WILDCARD = {"0.0.0.0", "::", ":::"}

_TCP_STATES = {"0A": "LISTEN"}

# /proc/net/tcp column layout, whitespace separated:
#   0 sl | 1 local | 2 remote | 3 state | 4 tx:rx | 5 tr:tm | 6 retrnsmt | 7 uid
#   8 timeout | 9 inode
_IDX_LOCAL, _IDX_STATE, _IDX_UID, _IDX_INODE = 1, 3, 7, 9


def decode_address(hex_address: str) -> str:
    """Decode a /proc/net/tcp address field (little-endian hex) to a string."""
    if ":" not in hex_address:
        return hex_address
    host_hex = hex_address.split(":", 1)[0]
    if len(host_hex) == 8:  # IPv4, 4 bytes, little-endian
        octets = [str(int(host_hex[i : i + 2], 16)) for i in (6, 4, 2, 0)]
        return ".".join(octets)
    if len(host_hex) == 32:  # IPv6, 4 little-endian words
        words = [host_hex[i : i + 8] for i in range(0, 32, 8)]
        grouped = "".join(word[6:8] + word[4:6] + word[2:4] + word[0:2] for word in words)
        # IPv6Address, not ip_address(): an all-zero or low-value address would
        # otherwise come back as 0.0.0.0 / 0.0.0.1 instead of :: / ::1.
        return str(ipaddress.IPv6Address(int(grouped, 16)))
    return host_hex


def decode_port(hex_port: str) -> int:
    return int(hex_port, 16)


def classify_binding(address: str) -> dict:
    """What a bind address means for reachability.

    ``exposed`` is the flag that matters: True only when the socket answers on an
    interface that is not loopback, i.e. when something other than this host can
    reach it.
    """
    if address in _WILDCARD:
        return {
            "scope": SCOPE_PUBLIC,
            "exposed": True,
            "note": "every interface: LAN, Tailscale and anything the firewall lets in",
        }

    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return {"scope": SCOPE_OTHER, "exposed": False, "note": f"unparsed address {address}"}

    if ip.is_loopback:
        return {"scope": SCOPE_LOCALHOST, "exposed": False, "note": "this host only"}
    if ip in TAILSCALE_NET:
        return {"scope": SCOPE_TAILSCALE, "exposed": True, "note": "Tailscale network only"}
    if any(ip in net for net in CONTAINER_NETS):
        return {"scope": SCOPE_CONTAINER, "exposed": False, "note": "container bridge"}
    if any(ip in net for net in LINK_LOCAL_NETS):
        return {"scope": SCOPE_LINK_LOCAL, "exposed": False, "note": "link-local only"}
    if any(ip in net for net in LAN_NETS):
        return {"scope": SCOPE_LAN, "exposed": True, "note": "private network address"}
    if ip.is_unspecified:
        return {"scope": SCOPE_PUBLIC, "exposed": True, "note": "unspecified address"}
    if ip.is_private:
        return {"scope": SCOPE_LAN, "exposed": True, "note": "private address"}
    return {"scope": SCOPE_OTHER, "exposed": True, "note": "routable address"}


def parse_proc_net(text: str, protocol: str) -> list[dict]:
    """Parse one ``/proc/net/tcp*`` table into listening sockets."""
    rows: list[dict] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        local = parts[_IDX_LOCAL]
        state = parts[_IDX_STATE].upper()
        remote_is_unset = parts[2].split(":", 1)[1] == "0000"
        if protocol == "tcp":
            if state not in _TCP_STATES:
                continue
        else:
            # UDP has no LISTEN state; an unconnected socket (07) with no remote
            # port is the equivalent, everything else is an active flow.
            if state != "07" or not remote_is_unset:
                continue
        if ":" not in local:
            continue
        host_hex, port_hex = local.rsplit(":", 1)
        address = decode_address(f"{host_hex}:0")
        port = decode_port(port_hex)
        try:
            # int, not str: the inode is the join key against /proc/<pid>/fd, and
            # a str/int mismatch there silently costs every attribution.
            inode = int(parts[_IDX_INODE])
        except (ValueError, IndexError):
            inode = None
        # A row can appear twice (v4 and v6 wildcard); the caller deduplicates
        # by (port, protocol) preferring the address that is more specific.
        rows.append(
            {
                "port": port,
                "protocol": protocol,
                "address": address,
                "inode": inode,
                "uid": parts[_IDX_UID],
                "state": state,
            }
        )
    return rows


def _read_tables(host_proc: str) -> tuple[list[dict], list[str]]:
    root = Path(host_proc) / "net"
    sockets: list[dict] = []
    errors: list[str] = []
    for filename, protocol in (
        ("tcp", "tcp"),
        ("tcp6", "tcp"),
        ("udp", "udp"),
        ("udp6", "udp"),
    ):
        try:
            text = (root / filename).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{filename}: {exc.strerror or exc}")
            continue
        sockets.extend(parse_proc_net(text, protocol))
    return sockets, errors


def scan_inode_owners(host_proc: str) -> dict[int, int]:
    """Map socket inode -> pid by walking /proc/<pid>/fd.

    The kernel's socket tables carry an inode per socket; the fds point back at
    it. Doing this walk ourselves beats asking a library, because a single
    unreadable /proc/<pid> must not cost us the other 400 attributions - and in
    a container it does: the capability to read fd directories is exactly the
    part that is missing by default.
    """
    owners: dict[int, int] = {}
    root = Path(host_proc)
    try:
        entries = list(os.scandir(root))
    except OSError:
        return owners

    for entry in entries:
        if not entry.name.isdigit():
            continue
        fd_dir = f"{root}/{entry.name}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue  # not ours to read; the socket simply stays unattributed
        pid = int(entry.name)
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                try:
                    owners.setdefault(int(target[8:-1]), pid)
                except ValueError:
                    continue
    return owners


def _attribution() -> tuple[dict[tuple[int, str], int], str | None]:
    """(port, protocol) -> pid, from psutil. Second choice behind the fd scan."""
    by_port: dict[tuple[int, str], int] = {}
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError) as exc:
        return {}, f"process attribution needs root: {exc}"
    except OSError as exc:
        return {}, f"process attribution unavailable: {exc}"

    for conn in connections:
        if conn.pid is None or not conn.laddr:
            continue
        protocol = "udp" if conn.type == 2 else "tcp"  # SOCK_DGRAM == 2
        by_port.setdefault((conn.laddr.port, protocol), conn.pid)
    return by_port, None


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return "?"


def snapshot(settings: Settings) -> dict:
    sockets, errors = _read_tables(settings.host_proc)
    if sockets:
        errors = []

    inode_owners = scan_inode_owners(settings.host_proc)
    by_port, attribution_error = _attribution()

    # One row per (port, protocol): prefer the specific address over a wildcard
    # so that a service bound to the LAN is not hidden behind another 0.0.0.0 row.
    best: dict[tuple[int, str], dict] = {}
    for sock in sockets:
        key = (sock["port"], sock["protocol"])
        current = best.get(key)
        if current is None or (current["address"] in _WILDCARD and sock["address"] not in _WILDCARD):
            best[key] = sock

    rows: list[dict] = []
    for (port, protocol), sock in best.items():
        binding = classify_binding(sock["address"])
        pid = inode_owners.get(sock.get("inode") or 0) or by_port.get((port, protocol))
        owner = resolve_owner(pid, settings.host_proc) if pid else None
        rows.append(
            {
                "port": port,
                "protocol": protocol,
                "address": sock["address"],
                "scope": binding["scope"],
                "exposed": binding["exposed"],
                "note": binding["note"],
                "process": _process_name(pid) if pid else None,
                "pid": pid,
                "owner_kind": (owner or {}).get("kind"),
                "owner": (owner or {}).get("name"),
            }
        )

    rows.sort(key=lambda r: (not r["exposed"], r["port"]))

    summary = {
        "total": len(rows),
        "exposed": sum(1 for r in rows if r["exposed"]),
        "localhost": sum(1 for r in rows if r["scope"] == SCOPE_LOCALHOST),
        "tailscale": sum(1 for r in rows if r["scope"] == SCOPE_TAILSCALE),
        "lan": sum(1 for r in rows if r["scope"] == SCOPE_LAN),
        "public": sum(1 for r in rows if r["scope"] == SCOPE_PUBLIC),
        "container": sum(1 for r in rows if r["scope"] == SCOPE_CONTAINER),
        "by_container": sum(1 for r in rows if r["owner_kind"] == KIND_CONTAINER),
        "by_service": sum(1 for r in rows if r["owner_kind"] == KIND_SERVICE),
        "by_user": sum(1 for r in rows if r["owner_kind"] == KIND_USER),
        "unattributed": sum(1 for r in rows if r["pid"] is None),
    }

    error = "; ".join(errors) if errors else attribution_error
    return {"ports": rows, "summary": summary, "error": error}
