# Roans Server Manager

One page that answers: what is running on this server, what is listening, what
is in Docker, and what is reachable from where.

Built for a single server and a single user. Read-only by default, bound to
`127.0.0.1` on purpose, no accounts and no multi-tenancy.

## What it shows

| Module | Question it answers | Source |
|---|---|---|
| System | load, memory, disk, uptime | `/proc`, `/sys` |
| Processes | what is running and what it costs | `/proc` |
| Docker | which containers are up, with what ports | Docker socket |
| Ports | every listening port and **what it is bound to** (localhost / LAN / Tailscale / public) | `/proc/net/tcp*`, `/proc/<pid>/cgroup` |
| Services | non-Docker programs, resolved to their systemd unit | `/proc/<pid>/cgroup` |

The panel shows one of these at a time, picked from a left sidebar: Overview
(system), Ports, Docker, Other programs (the services above) and Processes. Each
entry carries its live count, taken from the same poll that draws the page.

The port view is the point of the thing: the interesting question is never
"which port is open", it is "which port is open to the world".

## Run it

```bash
cp .env.example .env          # optional: set SM_TOKEN to require a token
docker compose up -d --build
```

Then open <http://127.0.0.1:8303>.

Requirements: Docker with Compose v2, a `docker` group membership for the socket
(replace), and Linux (the collectors read `/proc`).

## How it runs

The container uses `network_mode: host` and reads the host's `/proc`, `/sys`
and Docker socket. That is deliberate: a container's own `/proc` knows nothing
about the host's processes or listening sockets, so a port overview from inside
a bridged container network would describe the wrong machine.

Because host networking removes the container boundary, the bind address is the
only access control left:

```
uvicorn servermanager.web.app:app --host 127.0.0.1 --port 8303
```

Never change that to `0.0.0.0`. Remote access goes over Tailscale.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
SM_DEV=1 .venv/bin/python -m uvicorn servermanager.web.app:app --host 127.0.0.1 --port 8303 --reload
```

`./web` is bind-mounted read-only into the container, so frontend edits need a
browser reload and no rebuild.

## Status

Work is tracked on the [project board](https://github.com/users/roanh47/projects/5);
`docs/BACKLOG.md` explains the why behind each item. See `AGENTS.md` for the
rules — including "read the board before starting anything".

## License

All Rights Reserved. See `LICENSE`.
