// Roans Server Manager - one poll, one render.
//
// The whole page is drawn from /api/overview. Anything the backend could not
// read arrives as an error string and is shown as such: an empty panel always
// says why it is empty.

const REFRESH_MS = 5000;
const TOKEN_KEY = "sm_token";
const VIEW_KEY = "sm_view";

// One entry per sidebar item; the order here is the order in the DOM.
const VIEWS = ["overview", "ports", "docker", "programs", "processes"];

const $ = (id) => document.getElementById(id);

function token() {
  const fromUrl = new URLSearchParams(location.search).get("token");
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl);
    return fromUrl;
  }
  return localStorage.getItem(TOKEN_KEY) || "";
}

async function get(path) {
  const t = token();
  const headers = t ? { "X-SM-Token": t } : {};
  const res = await fetch(path, { headers, cache: "no-store" });
  if (res.status === 401) {
    const err = new Error("token required");
    err.status = 401;
    throw err;
  }
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

function bytes(n) {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

function duration(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

function ago(iso) {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const s = Math.max(0, (Date.now() - then) / 1000);
  return `${duration(s)} ago`;
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function table(headers, rows, empty) {
  if (!rows.length) return `<div class="empty">${esc(empty)}</div>`;
  const head = headers.map((h) => `<th>${esc(h)}</th>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function kpi(label, value, foot, cls) {
  return `<div class="kpi ${cls || ""}">
    <div class="label">${esc(label)}</div>
    <div class="value">${esc(value)}</div>
    <div class="foot">${esc(foot || "")}</div>
  </div>`;
}

function renderKpis(data) {
  const sys = data.system || {};
  const mem = sys.memory || {};
  const root = (sys.disks || [])[0] || {};
  const dock = data.containers || {};
  const prts = (data.ports || {}).summary || {};

  const cpuClass = sys.cpu_percent >= 90 ? "alarm" : sys.cpu_percent >= 70 ? "warn" : "";
  const memClass = mem.percent >= 90 ? "alarm" : mem.percent >= 75 ? "warn" : "";
  const load1 = (sys.load || {})["1m"];

  $("kpis").innerHTML = [
    kpi("CPU", `${sys.cpu_percent ?? "—"}%`, `${sys.cpu_count ?? "—"} threads · load ${load1 ?? "—"}`, cpuClass),
    kpi("Memory", `${mem.percent ?? "—"}%`, `${bytes(mem.used_bytes)} of ${bytes(mem.total_bytes)}`, memClass),
    kpi("Disk", `${root.percent ?? "—"}%`, `${root.mount || "—"} · ${bytes(root.used_bytes)} of ${bytes(root.total_bytes)}`),
    kpi("Uptime", duration(sys.uptime_seconds), `${sys.process_count ?? "—"} processes`),
    kpi("Containers", `${dock.running ?? 0}/${dock.count ?? 0}`, dock.unhealthy ? `${dock.unhealthy} unhealthy` : `image ${esc(sys.arch || "")}`, dock.unhealthy ? "alarm" : ""),
    kpi("Ports", `${prts.total ?? 0}`, `${prts.exposed ?? 0} reachable beyond loopback`, prts.exposed ? "warn" : ""),
  ].join("");
}

function renderPorts(data) {
  const prts = data.ports || {};
  $("ports-hint").textContent = `${prts.summary?.exposed ?? 0} of ${prts.summary?.total ?? 0} reachable beyond loopback`;
  const rows = (prts.ports || []).map((p) => `<tr>
      <td class="num mono">${p.port}</td>
      <td class="muted">${esc(p.protocol)}</td>
      <td><span class="scope ${esc(p.scope)}">${esc(p.scope)}</span></td>
      <td class="mono">${esc(p.address)}</td>
      <td>${esc(p.process || "—")}${p.owner ? ` <span class="muted">${esc(p.owner)}</span>` : ""}</td>
      <td class="muted">${esc(p.note || "")}</td>
    </tr>`);
  $("ports-body").innerHTML =
    (prts.error ? `<div class="error">${esc(prts.error)}</div>` : "") +
    table(["port", "proto", "scope", "bound to", "process", "means"], rows, "nothing is listening");
}

function renderDocker(data) {
  const dock = data.containers || {};
  $("docker-hint").textContent = `${dock.running ?? 0} running of ${dock.count ?? 0}`;
  const rows = (dock.containers || []).map((c) => {
    const status = c.health === "unhealthy"
      ? '<span class="pill bad">unhealthy</span>'
      : c.running ? '<span class="pill up">up</span>' : '<span class="pill down">stopped</span>';
    const ports = (c.ports || [])
      .filter((p) => p.host_port)
      .map((p) => `${p.host_ip === "0.0.0.0" ? '<span class="scope lan">all</span> ' : ""}${p.host_port}→${p.container_port}`)
      .join(", ");
    return `<tr>
      <td>${status}</td>
      <td>${esc(c.name)}</td>
      <td class="muted mono">${esc(c.image)}</td>
      <td class="mono">${ports || '<span class="muted">no published ports</span>'}</td>
      <td class="muted">${esc(c.compose_project || "")}</td>
    </tr>`;
  });
  $("docker-body").innerHTML =
    (dock.error ? `<div class="error">${esc(dock.error)}</div>` : "") +
    table(["", "name", "image", "ports", "project"], rows, "no containers");
}

function renderServices(data) {
  const svc = data.services || {};
  $("services-hint").textContent = `${svc.count ?? 0} units · ${svc.container_processes ?? 0} processes in containers`;
  const rows = (svc.units || []).map((u) => `<tr>
      <td>${esc(u.name)}</td>
      <td class="muted">${esc(u.kind)}</td>
      <td class="num mono">${u.process_count}</td>
      <td class="num mono">${u.cpu_percent}</td>
      <td class="num mono">${bytes(u.rss_bytes)}</td>
      <td class="mono">${esc(u.main_process)}</td>
    </tr>`);
  $("services-body").innerHTML =
    (svc.error ? `<div class="error">${esc(svc.error)}</div>` : "") +
    table(["unit", "kind", "procs", "cpu %", "rss", "main"], rows, "no host units found");
}

function renderProcesses(data) {
  const procs = data.processes || {};
  $("processes-hint").textContent = `${procs.count ?? 0} processes, top ${(procs.processes || []).length} by CPU`;
  const rows = (procs.processes || []).map((p) => `<tr>
      <td class="num mono">${p.pid}</td>
      <td>${esc(p.name)}</td>
      <td class="muted">${esc(p.user)}</td>
      <td class="num mono">${p.cpu_percent}</td>
      <td class="num mono">${p.memory_percent}</td>
      <td class="num mono">${bytes(p.rss_bytes)}</td>
      <td class="muted">${esc(p.owner_kind === "service" ? p.owner : "")}</td>
    </tr>`);
  $("processes-body").innerHTML =
    (procs.error ? `<div class="error">${esc(procs.error)}</div>` : "") +
    table(["pid", "name", "user", "cpu %", "mem %", "rss", "owner"], rows, "no processes");
}

// --- sidebar ---------------------------------------------------------------
// Which view is shown is client state only: the server keeps serving the whole
// overview and this only decides what is visible, so switching costs nothing
// and a slow poll can never leave a view blank.

function currentView() {
  const fromHash = (location.hash || "").replace("#", "");
  if (VIEWS.includes(fromHash)) return fromHash;
  const saved = localStorage.getItem(VIEW_KEY) || "";
  return VIEWS.includes(saved) ? saved : "overview";
}

function setView(name) {
  const active = VIEWS.includes(name) ? name : "overview";
  VIEWS.forEach((v) => {
    const section = $(`view-${v}`);
    if (section) section.classList.toggle("hidden", v !== active);
  });
  document.querySelectorAll("nav.side .nav-item").forEach((btn) => {
    btn.setAttribute("aria-current", btn.dataset.view === active ? "true" : "false");
  });
  localStorage.setItem(VIEW_KEY, active);
  if (location.hash !== `#${active}`) history.replaceState(null, "", `#${active}`);
}

function renderBadges(data) {
  const prts = (data.ports || {}).summary || {};
  const dock = data.containers || {};
  const svc = data.services || {};
  const procs = data.processes || {};
  const set = (id, text) => { const el = $(id); if (el) el.textContent = text; };
  set("nav-ports", prts.total || "");
  set("nav-docker", dock.count ? `${dock.running ?? 0}/${dock.count}` : "");
  set("nav-programs", svc.count || "");
  set("nav-processes", procs.count || "");
}

function render(data) {
  const sys = data.system || {};
  $("server-name").textContent = data.server || sys.hostname || "server";
  $("host-line").textContent =
    `${sys.hostname || ""} · ${sys.os || ""} · ${sys.cpu_model || ""} · up ${duration(sys.uptime_seconds)}`;
  $("stamp").textContent = new Date().toLocaleTimeString();
  renderKpis(data);
  renderBadges(data);
  renderPorts(data);
  renderDocker(data);
  renderServices(data);
  renderProcesses(data);
}

let timer = null;

async function tick() {
  try {
    const data = await get("/api/overview");
    $("conn").className = "dot live";
    $("token-banner").classList.add("hidden");
    render(data);
  } catch (err) {
    if (err.status === 401) {
      $("conn").className = "dot dead";
      $("token-banner").classList.remove("hidden");
      return;
    }
    $("conn").className = "dot dead";
    $("stamp").textContent = String(err.message || err);
  }
}

function start() {
  tick();
  if (timer) clearInterval(timer);
  timer = setInterval(tick, REFRESH_MS);
}

document.querySelectorAll("nav.side .nav-item").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});
window.addEventListener("hashchange", () => setView(currentView()));

$("refresh").addEventListener("click", tick);
$("token-save").addEventListener("click", () => {
  localStorage.setItem(TOKEN_KEY, $("token-input").value.trim());
  $("token-banner").classList.add("hidden");
  tick();
});
$("token-input").addEventListener("keydown", (e) => { if (e.key === "Enter") $("token-save").click(); });

setView(currentView());
start();
