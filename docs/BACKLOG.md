# Backlog — why each item exists

**The board is the status. This file is the reason.**

Item titles below match the issues on
[Roans Server Manager · project 5](https://github.com/users/roanh47/projects/5)
one-for-one; a test enforces that. Never write a status column here — status
lives on the board, so it cannot be stale in two places at once.

## 1 — General file structure, AGENTS.MD, README.MD and License

A repo that two agents work in needs its rules written down before the code
starts contradicting them. AGENTS.md carries the bind-to-loopback rule, the
board workflow and the definition of done; README.md is the five-minute version
for a human; the license is all-rights-reserved so nothing here is offered as a
product.

## 2 — File browser

Browse the server's filesystem from the same page, read-only. Replaces the
"ssh in to look at a file" detour. Needs a deliberate mount decision (host `/`
read-only, roots allow-listed) which is why it is its own item rather than part
of the base program.

## 3 — Terminal

A web terminal for the same reason the file browser exists: stop needing a
separate SSH session for a one-line check. This is the single most dangerous
capability in the panel — a shell in the container, with the host's `/proc` and
the Docker socket mounted, is effectively root on the server. It ships behind
three conditions or it does not ship: loopback-only bind, a token that must be
set (not optional) before the terminal is enabled, and no host `/` mount.

## 4 — Port overview

What is listening, on which address, and therefore who can reach it. Built
first among the read-only views because it answers the security question the
other views cannot: a service on `0.0.0.0` is a different thing from the same
service on `127.0.0.1`, and nothing else on the box tells you which is which
without reading a man page.

## 5 — Docker overview

Containers, images, state and published ports, from the Docker socket. This
server runs its services as containers, so this is the real "what is up"
list — including the containers that are running but unhealthy, which a `docker
ps` glance hides.

## 6 — Running programs

The top processes by CPU and memory. The panel should let you see a runaway
process without typing `top`, and see which systemd unit or container owns it.

## 7 — Other programs

Everything on the host that is not in Docker: systemd units, user sessions and
the unmanaged remainder, grouped and attributed via `/proc/<pid>/cgroup`. The
gap this closes is the classic one — a service started by hand six months ago
that nobody remembers, still holding a port.

## 8 — Base program / webui

The panel itself: a Dockerised web UI bound to `127.0.0.1`, serving one page
that reads the collectors above. Everything else is a panel inside this.

## 9 — Left sidebar navigation

Every panel currently stacks down one page: KPIs, Ports, Docker, Other programs,
Processes. That reads fine at 57 ports and becomes unusable the moment the file
browser and the terminal (items 2 and 3) land, because there is nowhere to put
them that is not the bottom of an ever-growing scroll.

So the panel gets a left sidebar with one entry per view - Overview, Ports,
Docker, Other programs, Processes - and shows a single view at a time. The choice
is kept in the URL hash and in localStorage, so a refresh stays where you were
and a link to `#ports` opens on ports. Each entry carries the live count from the
same `/api/overview` call that already feeds the page (ports, containers, units,
processes), which is what earns the sidebar its width: the number is visible
without switching to the view.

Rejected: tabs or a dropdown along the top - both collapse badly on a phone and
neither has room for a count. Rejected as well: fetching per view, which would
cost a request on every switch and show an empty panel while it lands; the poll
stays one call and switching is a class change over data that is already there.

This is still read-only. The sidebar is a filter over what is already collected:
no new route, no action, no server-side state.
