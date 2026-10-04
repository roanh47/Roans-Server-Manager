# AGENTS.md — how to work in this repo

This file is binding for any agent (or human) working here. Read it before the
first edit, not after the first mistake.

## Status tracking: GitHub Projects, always

**The board is the source of truth for state. The backlog file carries the why.**

- Board: <https://github.com/users/roanh47/projects/5> — project **5**,
  owner `roanh47`, title *Roans Server Manager*.
- Why-file: [`docs/BACKLOG.md`](docs/BACKLOG.md) — one section per board item,
  explaining the problem, the intended behaviour and what was rejected.

Rules:

1. **Before starting work, read the board** and pick an item that is `Ready` or
   `Backlog`. Never invent work that has no item — add the item first.
2. **Move the item to `In progress`** when you start it, and to `Done` only when
   it is actually verified running. `In review` is for work that is pushed but
   not verified.
3. **Never put a status column in `docs/BACKLOG.md`.** Two places claiming to
   know the state is how they drift apart. `tests/test_backlog.py` fails the
   build if the board and the file disagree on which items exist.
4. New work discovered mid-task becomes a **new board item** (with a section in
   the backlog file), not a silent side quest.

```bash
gh project item-list 5 --owner roanh47 -L 200        # what is on the board
gh project field-list 5 --owner roanh47              # Status / Priority / Size ids
gh project item-list 5 --owner roanh47 -L 200 --format json   # item ids for edits
gh project item-edit --id <ITEM_ID> --project-id PVT_kwHOBpzE0s4BljtE \
  --field-id PVTSSF_lAHOBpzE0s4BljtEzhkQHS0 --single-select-option-id 47fc9ee4  # In progress
```

Status option ids: `Backlog f75ad846` · `Ready 61e4505c` · `In progress 47fc9ee4`
· `In review df73e18b` · `Done 98236657`.

## What this program is

A **single-user** control panel for one server (`Roans-Server`): what is
running, what is listening, what is in Docker, and what those things are bound
to. It is a read-and-observe tool with a shell attached later; it is not a
multi-user product, it has no accounts, no signup and no tenancy.

## Binding rules (non-negotiable)

- **The web UI binds `127.0.0.1` only.** Never `0.0.0.0`, never the LAN
  address. Remote access happens over Tailscale or a tunnel, never by
  widening the bind. This is the whole reason the port overview exists.
- **The container runs with `network_mode: host`** so that the port and process
  views describe the *host*, not the container. That makes the bind line above
  the only thing standing between this panel and the internet — treat it as
  load-bearing.
- If `SM_TOKEN` is set, every `/api/*` route requires it (`X-SM-Token` header,
  `Authorization: Bearer`, or `?token=`). `/healthz` stays open so the
  container healthcheck works.
- Two locks before any state-changing action is added later: the action must be
  enabled in config **and** the request must carry the token. Read-only by
  default.

## House rules for this repo

- **License is All Rights Reserved** (see `LICENSE`, copied from
  Roans-Banking-Dashboard). Do not add a permissive license, do not add a
  `LICENSE` header that promises rights we do not grant.
- **No secrets in the repo.** `.env` is gitignored; `.env.example` documents
  every variable. Run the secret scan before pushing:
  `git diff | grep -E "ghp_|ci_live|APCA[A-Z0-9]{10}|BEGIN (RSA|OPENSSH) PRIVATE KEY"`.
- **Tests before commit.** `python -m pytest -q` must be green, and new
  behaviour needs a test that would fail without the change.
- **Config is not baked into the image.** `./config` is bind-mounted read-only;
  changing it must never require a rebuild.
- **Ports:** this program owns `127.0.0.1:8303`. It does not take a port that
  another program already holds (8300 OSINT, 8301 skin flipper, 8302 trading,
  8642 Hermes). Adding a service means checking `ss -tlnp` first.
- **No fabricated data in the UI.** If a collector cannot reach its source, it
  returns an explicit unavailable/error field and the UI says so. Never show a
  made-up number.
- Prefer `pathlib`, type hints, and small functions that read a single source
  (`/proc/net/tcp`, the Docker socket, `/proc/<pid>/cgroup`).

## Layout

```
servermanager/collectors/   one module per data source, no web imports
servermanager/web/app.py    FastAPI routes; thin, delegates to collectors
web/                        static frontend, bind-mounted, no rebuild needed
docs/BACKLOG.md             the why behind every board item
tests/                      pytest; test_backlog.py enforces the board split
```

## Definition of done

1. The item's behaviour works **against the real host** (not a mock) - show the
   command output.
2. `python -m pytest -q` is green.
3. The board item is moved to `Done` and `docs/BACKLOG.md` still matches the
   board.
4. Pushed to `main` with a message that says what changed and why.
