# Architecture

## Shape

```
browser ──HTTP──▶ 127.0.0.1:8303 (uvicorn, in container)
                     │
                     ├── /api/*      collectors/*  ──▶ /proc, /sys, docker.sock
                     └── /           web/ (static)
```

One process, one page, one poll every five seconds. There is no database and no
state: every render reads the machine as it is right now. If the panel is down
it has forgotten nothing.

## Why the container is not isolated (and what that costs)

The panel's job is to describe the *host*, so the container is deliberately
joined to it:

- `network_mode: host` — otherwise `/proc/net/tcp` describes the container's own
  network namespace and the port list would be a lie.
- `pid: host` — so the process list is the server's, not the panel's.
- `uts: host` — so the hostname is the server's.
- `/proc` and `/sys` mounted read-only at `/host/proc` and `/host/sys`, and
  `psutil.PROCFS_PATH` pointed at `/host/proc`.
- `/var/run/docker.sock` — container list.

`network_mode: host` is also why the bind address matters more than usual: with
the host network namespace there is no port mapping to keep the panel private,
only `--host 127.0.0.1`. That flag is the entire security boundary, which is why
AGENTS.md treats changing it as an explicit decision rather than a tweak.

Read-only mounts and a read-only API: no route starts, stops, restarts or
writes anything. Restarting a service is a future item, and it will arrive with
an audit trail, not as a bare button.

## Collectors

| module | source | answers |
| --- | --- | --- |
| `system.py` | psutil over host `/proc`, `/sys` | what is this machine, how loaded |
| `processes.py` | psutil process table | what is eating CPU/memory |
| `containers.py` | docker socket | what is up, what is unhealthy, what is published |
| `ports.py` | `/proc/net/tcp{,6}`, `/proc/net/udp{,6}` + `psutil.net_connections` | what listens and who can reach it |
| `services.py` | `/proc/<pid>/cgroup` | which unit or container owns a process |

Each collector returns a dict whose `error` key is `None` or a human sentence.
No collector raises at the edges: the page degrades one panel at a time.

## Port scope classification

The bind address is the ground truth, so `classify_binding()` maps it:

| address | scope | reachable from outside the host |
| --- | --- | --- |
| `127.0.0.1`, `::1` | localhost | no |
| `100.64.0.0/10` | tailscale | yes, tailnet only |
| `172.17–172.31`, `10.88` | container | no |
| `10/8`, `172.16/12`, `192.168/16` | lan | yes, private network |
| `0.0.0.0`, `::` | public | yes, every interface |
| anything routable | other | yes |

`exposed: true` on a wildcard bind means "whatever the firewall allows gets
in", which is the honest phrasing — the panel cannot see the router and does not
pretend to.

## Files

```
servermanager/
  config.py               environment -> Settings, nothing else
  collectors/             read-only data sources (no web imports)
  web/app.py              routes, token guard, static mount
web/                      one page: index.html, css, js
docs/                     this file, BACKLOG.md, AGENTS.md at root
tests/                    unit tests plus live smoke tests
```
