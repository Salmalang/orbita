/* ARGOS — control-room UI (Preact + htm, no build step). */
const { html, render, useState, useEffect, useRef, useMemo, useCallback } = htmPreact;

// ------------------------------------------------------------------ api
async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map(x => x.msg).join("; ") : (d || r.statusText));
  }
  return data;
}

// ------------------------------------------------------------------ helpers
const LEVEL_TEXT = { NORMAL: "Normal", WATCH: "Attention", HIGH: "Warning", CRITICAL: "Critical alert", NO_DATA: "No live data", STANDBY: "Not started" };
const LEVEL_ICON = { NORMAL: "✓", WATCH: "●", HIGH: "▲", CRITICAL: "⚠", NO_DATA: "?", STANDBY: "○" };
const plainReason = (r) => !r ? "" : r.includes("coincidence rule met") ? "Two or more sensors agree: this looks like a fire."
  : r.includes("waiting for a second node") ? "One sensor shows a possible fire. Waiting for a second sensor to confirm."
  : r.includes("process nuisance") ? "Smoke or fumes detected, most likely from normal work (welding, cutting, engines). Not a fire."
  : r.includes("rising fire signal") ? "Unusual air on some sensors, possibly the start of a fire. Watching closely."
  : r.includes("No sensor node is delivering live data") ? "Sensors are not sending live readings. The hall status is unknown."
  : r.includes("All healthy nodes") ? "All sensors look normal." : r;
const nodeCond = (n, id, dec) => !n ? ["NO_DATA", "? waiting for data"] : dec?.unhealthy_nodes?.includes(id) ? ["NO_DATA", "? no live data"]
  : dec?.fire_nodes?.includes(id) ? ["CRITICAL", "⚠ fire signal"] : n.p_fire >= 0.5 ? ["HIGH", "▲ possible fire"]
  : n.p_nuisance >= 0.5 ? ["WATCH", "● work fumes"] : ["NORMAL", "✓ normal"];
const eventTitle = (e) => ({
  risk_level_changed: `Status changed to ${LEVEL_TEXT[e.payload.to] || e.payload.to}`, alert: `Alert: ${LEVEL_TEXT[e.payload.level] || e.payload.level}`,
  case_opened: "Incident follow-up opened", technician_action: "Intervention recorded", verification_approved: "Work verified by a second person",
  verification_rejected: "Verification refused", stabilization_check: e.payload.passed ? "Recovery confirmed" : "Recovery not yet confirmed",
  closure_check: e.payload.passed ? "Follow-up inspection confirmed" : "Follow-up inspection not yet confirmed", case_closed: "Incident closed",
  replay_loaded: `Recording loaded: ${e.payload.event_id}`, demo_reset: "Demo reset", mission_created: "Drone inspection created",
  mission_approve: "Drone flight approved", mission_completed: "Drone inspection finished", checkpoint_inspected: `Drone checked: ${e.payload.label}`,
  inspection_finding: `Drone finding (illustrative): ${e.payload.type}`, checkpoint_clear: `Marked clear: ${e.payload.checkpoint}`,
  replay_auto_paused: "Replay paused for the response", outcome_confirmed: "Real outcome confirmed by a second person",
  hedera_anchor_submitted: "Evidence fingerprint sent to Hedera", hedera_verification: `Hedera check: ${e.payload.status}`,
  learning_dataset_prepared: `Learning dataset ${e.payload.dataset_version} prepared`, emergency_pack_issued: "Firefighter emergency pack issued (QR link)",
  emergency_pack_revoked: "Firefighter emergency pack link revoked", emergency_pack_opened: "Firefighter briefing opened by a responder", patrol_schedule_set: "Patrol schedule updated", mission_cancel: "Drone inspection cancelled",
  mission_pause: "Drone inspection paused", mission_resume: "Drone inspection resumed", case_escalated: "Fire signal still present after the intervention",
}[e.kind] || e.kind);
const LEVEL_COLOR = { NORMAL: "#2E7D4F", WATCH: "#2F5F98", HIGH: "#9A5B00", CRITICAL: "#B3261E", NO_DATA: "#9A9088" };
const SRC = {
  sensor: "Recorded sensor data", model: "Model output", risk: "Risk engine", human: "Human action (demo role)",
  system: "System", simulated: "Simulated workflow",
};
const fmtT = (iso, withDate) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const t = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" });
  return withDate ? `${d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })} ${t} UTC` : t;
};
const fmtWall = (iso) => iso ? new Date(iso).toLocaleTimeString("en-GB") : "—";
const pct = (x) => x == null ? "—" : `${(x * 100).toFixed(x < 0.1 ? 1 : 0)}%`;
const num = (x, d = 1) => x == null || Number.isNaN(x) ? "—" : Number(x).toFixed(d);
const nodeColor = (n, fireNodes) => !n ? "#9A9088" : fireNodes?.includes(n.id) ? LEVEL_COLOR.CRITICAL
  : n.p_fire >= 0.5 ? LEVEL_COLOR.HIGH : n.p_nuisance >= 0.5 ? LEVEL_COLOR.WATCH : LEVEL_COLOR.NORMAL;

function useHash() {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => { const f = () => setH(location.hash || "#/"); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
}
function usePoll(fn, ms, deps = []) {
  useEffect(() => { let alive = true; const run = async () => { if (alive) await fn().catch(() => {}); };
    run(); const id = setInterval(run, ms); return () => { alive = false; clearInterval(id); }; }, deps);
}

// ------------------------------------------------------------------ chart component
function LineChart({ labels, series, yMax, yMin, height = 210, thresholds = [], unit }) {
  const ref = useRef(null), chart = useRef(null);
  useEffect(() => {
    chart.current = new Chart(ref.current, {
      type: "line",
      data: { labels: [], datasets: [] },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { color: "#6B6158", boxWidth: 12, font: { size: 12 } } },
                   tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y == null ? "—" : c.parsed.y.toFixed(3)}${unit ? " " + unit : ""}` } } },
        scales: {
          x: { ticks: { color: "#6B6158", maxTicksLimit: 7, autoSkip: true, font: { size: 11 } }, grid: { color: "rgba(41,42,41,.05)" } },
          y: { ticks: { color: "#6B6158", font: { size: 11 } }, grid: { color: "rgba(41,42,41,.07)" }, min: yMin, max: yMax },
        },
        elements: { point: { radius: 0 }, line: { borderWidth: 2.2, tension: 0.2 } },
      },
    });
    return () => chart.current.destroy();
  }, []);
  useEffect(() => {
    const c = chart.current; if (!c) return;
    c.data.labels = labels;
    c.data.datasets = [
      ...series.map(s => ({ label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.fill || "transparent", fill: !!s.fill, spanGaps: false })),
      ...thresholds.map(t => ({ label: t.label, data: labels.map(() => t.value), borderColor: t.color, borderDash: [5, 4], borderWidth: 1.2 })),
    ];
    c.update("none");
  }, [labels, series]);
  return html`<div class="chartbox" style=${`height:${height}px`}><canvas ref=${ref}></canvas></div>`;
}

// ------------------------------------------------------------------ hall map
function HallMap({ facility, nodes, fireNodes, onPick, picked, showExits = true, drone, mission }) {
  if (!facility) return null;
  const W = facility.dimensions_m.length, H = facility.dimensions_m.width, s = 40, px = 120, py = 34;
  const X = (x) => px + x * s, Y = (y) => py + y * s;
  const cpState = (id) => mission?.checkpoints.find(x => x.id === id);
  const short = (l) => l.split(" (")[0].split(",")[0];
  return html`<div class="map">
    <svg viewBox=${`0 0 ${W * s + px * 2} ${H * s + py * 2}`} role="img" aria-label="Production hall map with sensors, exits and drone checkpoints">
      <rect x=${px} y=${py} width=${W * s} height=${H * s} rx="12" fill="#FAF8F4" stroke="#C7C4BF" stroke-width="2"/>
      ${showExits && facility.exits.map(e => { const left = e.x === 0;
        return html`<g><rect x=${X(e.x) - 6} y=${Y(e.y) - 24} width="12" height="48" rx="3" fill="#2E7D4F"/>
        <text x=${left ? px - 14 : X(e.x) + 14} y=${Y(e.y) - 2} text-anchor=${left ? "end" : "start"} fill="#2E7D4F" font-size="13" font-weight="600">EXIT</text>
        <text x=${left ? px - 14 : X(e.x) + 14} y=${Y(e.y) + 15} text-anchor=${left ? "end" : "start"} fill="#6B6158" font-size="12">${e.label}</text></g>`; })}
      ${facility.drone_dock && html`<g><rect x=${X(facility.drone_dock.x) - 13} y=${Y(facility.drone_dock.y) - 13} width="26" height="26" rx="6" fill="#F0EBF2" stroke="#6A5677" stroke-dasharray="3 3"/>
        <text x=${X(facility.drone_dock.x) + 20} y=${Y(facility.drone_dock.y) + 4} fill="#6A5677" font-size="12">Drone base</text></g>`}
      ${mission && html`<polyline points=${mission.path.map(p => `${X(p.x)},${Y(p.y)}`).join(" ")} fill="none" stroke="#6A5677" stroke-width="2.5" stroke-dasharray="7 6" opacity=".7"/>`}
      ${facility.nodes.map(n => {
        const st = nodes?.[n.id]; const col = nodeColor(st && { ...st, id: n.id }, fireNodes);
        const cx = X(n.x), cy = Y(n.y);
        return html`<g style=${onPick ? "cursor:pointer" : ""} onClick=${() => onPick && onPick(n.id)}>
          ${fireNodes?.includes(n.id) && html`<circle cx=${cx} cy=${cy} r="28" fill="#B3261E" opacity=".14"/>`}
          <circle cx=${cx} cy=${cy} r="16" fill=${col} stroke=${picked === n.id ? "#292A29" : "#FFFFFF"} stroke-width="3"/>
          <text x=${cx} y=${cy + 4} text-anchor="middle" fill="#FFFFFF" font-size="10.5" font-weight="700">${n.label}</text>
        </g>`;
      })}
      ${drone && facility.checkpoints && facility.checkpoints.map(c => { const st = cpState(c.id);
        const fill = st?.result === "finding" ? "#9A5B00" : st?.status === "inspected" ? "#6A5677" : "#FFFFFF";
        const left = c.x < 3, right = c.x > W - 3;
        const cur = drone?.active && drone.active.id === mission?.id && (drone.active.current || "").includes(short(c.label));
        return html`<g>
          ${cur && html`<circle cx=${X(c.x)} cy=${Y(c.y)} r="17" fill="none" stroke="#6A5677" stroke-width="2"/>`}
          <rect x=${X(c.x) - 8} y=${Y(c.y) - 8} width="16" height="16" rx="2" transform=${`rotate(45 ${X(c.x)} ${Y(c.y)})`} fill=${fill} stroke="#6A5677" stroke-width="2"/>
          <text x=${left ? X(c.x) - 8 : right ? X(c.x) + 8 : X(c.x)} y=${left ? Y(c.y) - 16 : right ? Y(c.y) + 30 : Y(c.y) + (c.y < 2 ? -16 : 28)}
            text-anchor=${left ? "start" : right ? "end" : "middle"} fill="#4C3D57" font-size="12" font-weight="600">${short(c.label)}</text></g>`; })}
      ${drone?.active && (!mission || drone.active.id === mission.id) && html`<g transform=${`translate(${X(drone.active.position.x)} ${Y(drone.active.position.y)})`}>
        <circle r="15" fill="rgba(106,86,119,.18)"/>
        <path d="M-10 0 H10 M0 -10 V10" stroke="#292A29" stroke-width="2.5"/><circle r="5" fill="#6A5677" stroke="#FFF" stroke-width="1.5"/>
        <text y="-18" text-anchor="middle" fill="#292A29" font-size="12" font-weight="700">Drone (simulated)</text></g>`}
    </svg>
    <div class="legend"><span><i style="background:#2E7D4F"></i>✓ normal</span><span><i style="background:#2F5F98"></i>work smoke or fumes</span>
      <span><i style="background:#9A5B00"></i>▲ possible fire signal</span><span><i style="background:#B3261E"></i>⚠ fire signal confirmed</span><span><i style="background:#9A9088"></i>? no live data</span>
      ${drone ? html`<span><i style="background:#6A5677;border-radius:2px"></i>drone checkpoint (filled = inspected)</span>` : ""}<span class="dim">${facility.name} · ${W} × ${H} m · layout illustrative</span></div>
  </div>`;
}

function RiskBanner({ decision, compact }) {
  const lvl = decision?.level || "NO_DATA";
  const reasons = decision?.reasons || ["Choose a recorded event and start the replay"];
  return html`<div class=${`risk ${lvl}`}>
    <div class="lvl">${LEVEL_ICON[lvl]} ${LEVEL_TEXT[lvl]}</div>
    <div class="why">${plainReason(reasons[0])}</div>
    <div class="more">${compact ? "" : html`<details><summary>Technical details</summary>${reasons.join(" · ")}${decision ? ` · operational priority ${decision.score}/100 (not a probability)` : ""}</details>`}</div>
  </div>`;
}

// ------------------------------------------------------------------ pages
const GLOSS = {
  pfire: "AI fire likelihood: how much a sensor's readings look like a fire (0–100 %), learned from real recorded fires. A guide for people, not an exact probability.",
  replay: "Historical replay: real sensor readings recorded in an industrial hall during controlled experiments (July 2023), played back as if live.",
  sim: "Simulated: no physical drone is connected. Movement, schedules and findings demonstrate the workflow only.",
};
const Info = ({ k }) => html`<span class="info" title=${GLOSS[k]}>ⓘ</span>`;
const MODE_LABEL = { PREVENTIVE: "Routine inspection", TARGETED: "Alert inspection", FOLLOW_UP: "Follow-up inspection" };
const ORIGIN_LABEL = { SCHEDULED: "planned patrol", MANUAL: "started by the operator", ALERT: "requested by a sensor alert", FOLLOW_UP: "check after the intervention" };
const inMin = (iso) => { if (!iso) return "—"; const m = Math.round((new Date(iso) - Date.now()) / 60000); return m <= 0 ? "due now" : m < 60 ? `in ${m} min` : `in ${Math.floor(m / 60)} h ${m % 60} min`; };

function Overview({ ctx }) {
  const { facility, state, cases, drone } = ctx;
  const [recent, setRecent] = useState([]);
  usePoll(async () => setRecent((await api("/api/timeline?limit=12")).reverse()), 3000, []);
  const dec = state?.latest?.decision;
  const level = dec?.level;
  const open = cases.filter(c => c.status !== "CLOSED");
  const critical = open.filter(c => c.severity === "CRITICAL");
  const awaiting = (drone?.missions || []).filter(m => m.status === "AWAITING_APPROVAL");
  const loose = (drone?.findings || []).filter(f => !f.case_id);
  const active = drone?.active;
  const sched = (drone?.schedules || []).filter(s => s.enabled).sort((a, b) => a.next_due.localeCompare(b.next_due))[0];
  const route = (id) => drone?.routes?.find(r => r.id === id)?.label || id;
  const head = level === "CRITICAL" || critical.length ? ["CRITICAL", "Critical alert", "A fire signal has been confirmed. Respond now."]
    : level === "HIGH" ? ["HIGH", "Attention needed", "One sensor shows a possible fire signal. ARGOS is checking it."]
    : open.length || awaiting.length || loose.length ? ["WATCH", "Attention needed", "No fire signal right now, but some items need your action."]
    : !state?.event_id ? ["STANDBY", "Monitoring not started", "No sensor data is being received. ARGOS cannot say the hall is safe yet."]
    : level === "NO_DATA" ? ["NO_DATA", "Sensors not updating", "Sensor readings are not live. The status is unknown."]
    : ["NORMAL", "Normal monitoring", "All reporting sensors look normal."];

  const items = [];
  awaiting.forEach(m => items.push({ sev: "HIGH", where: m.checkpoints.map(c => c.label).join(", "), what: "Drone inspection waiting for your approval", when: m.created_at, href: "#/drone", b: "Review inspection", next: "Review the drone inspection" }));
  open.forEach(c => items.push({ sev: c.severity, where: c.kind === "INSPECTION_FINDING" ? (c.evidence?.finding?.checkpoint_label || c.zone) : `${facility?.name || c.zone} (sensors)`,
    what: c.kind === "INSPECTION_FINDING" ? c.findings[0] : "Fire signal detected by the sensors", when: c.opened_wall_ts, href: `#/cases/${c.id}`,
    b: "Open follow-up", next: c.status === "OPEN" ? "Inspect the equipment and record your intervention" : c.status === "ACTION_RECORDED" ? "Ask another authorized person to check the work" : "Check that the equipment is back to normal" }));
  loose.forEach(f => items.push({ sev: f.severity === "HIGH" ? "CRITICAL" : f.severity === "MEDIUM" ? "HIGH" : "WATCH", where: f.checkpoint_label, what: `${f.type_label} (drone finding, illustrative)`, when: f.recorded_at, href: "#/drone", b: "Review finding", next: "Review the drone finding" }));
  const order = { CRITICAL: 0, HIGH: 1, WATCH: 2 };
  items.sort((a, b) => (order[a.sev] ?? 3) - (order[b.sev] ?? 3));
  const next = items[0] || (state?.event_id ? { next: "Keep monitoring. Nothing needs your action.", href: "#/monitor", b: "Live monitoring" }
    : { next: "Start monitoring: replay a recorded event, or take the guided tour.", href: "#/monitor", b: "Start monitoring" });
  const nodes = state?.latest?.nodes || {};
  const sevLabel = { CRITICAL: "⚠ Critical", HIGH: "▲ High", WATCH: "● Medium" };

  return html`<div class="page">
    <div class=${`hero ${head[0]}`}>
      <div><div class="q">Facility status · ${facility?.name || ""}</div><div class="a">${head[1]}</div>
        <div class="sub2">${head[2]}${state?.event_id ? html` · historical replay of real data <${Info} k="replay"/>` : ""}</div></div>
      <div class="lvl">${LEVEL_ICON[head[0]]} ${LEVEL_TEXT[head[0]]}</div>
    </div>

    <div class="grid g-main">
      <div class="card"><h2>What needs attention <span class="r">${items.length ? `${items.length} item${items.length > 1 ? "s" : ""}` : ""}</span></h2>
        ${items.length ? items.slice(0, 6).map(x => html`<div class="attn">
            <span class=${`pill ${x.sev}`}>${sevLabel[x.sev] || x.sev}</span>
            <div class="what"><b>${x.what}</b><span>${x.where}</span></div>
            <span class="when">${fmtWall(x.when)}</span>
            <a class="btn sm" href=${x.href}>${x.b} →</a></div>`)
          : html`<div class="empty">✓ Nothing needs your attention right now.</div>`}
      </div>
      <div class="nextbox"><div class="q">What should I do next?</div><div class="a">${next.next}</div><a class="btn" href=${next.href}>${next.b} →</a></div>
    </div>

    <div class="grid g-main">
      <div class="card"><h2>Equipment and sensors · ${facility?.name} <span class="r muted">9 sensors</span></h2>
        <div class="equip">${(facility?.nodes || []).map(n => { const c = nodeCond(nodes[n.id], n.id, dec);
          return html`<div class="e"><b>Sensor ${n.label}</b><span class=${`pill ${c[0]}`}>${c[1]}</span></div>`; })}</div>
        <div class="muted" style="font-size:12.5px;margin-top:10px">${facility?.illustrative_note}</div>
      </div>
      <div class="stack">
        <div class="card"><h2>Drone patrols <span class="r"><span class="pill sim">simulated drone</span></span></h2>
          ${active ? html`<div><b>${active.mode === "PREVENTIVE" ? "Routine inspection running" : "Alert inspection running"}</b> · ${active.label}</div>
              <div class="bar"><i style=${`width:${Math.round(active.progress * 100)}%`}></i></div>
              <div class="muted">${active.status === "PAUSED" ? "Paused" : active.current || "Taking off"}</div>`
            : html`<div class="muted">The drone is at its base.</div>`}
          <div style="margin-top:8px">Next routine patrol: <b>${sched ? `${inMin(sched.next_due)}` : "none scheduled"}</b>${sched ? html` <span class="muted">(${route(sched.route_id)})</span>` : ""}</div>
          <div style="margin-top:4px">Findings waiting: <b>${loose.length}</b></div>
          <a class="btn sm" style="margin-top:10px" href="#/drone">Open drone inspections →</a></div>
        <div class="card"><h2>Recent activity</h2>
          ${recent.length ? recent.slice(0, 6).map(e => html`<div class="act"><span class="t">${fmtWall(e.wall_ts)}</span><span>${eventTitle(e)}</span></div>`)
            : html`<div class="empty">No activity yet.</div>`}</div>
      </div>
    </div>
  </div>`;
}

function Monitor({ ctx }) {
  const { facility, state, ticks, catalog, refresh, toast } = ctx;
  const [picked, setPicked] = useState(null);
  const [nodeHist, setNodeHist] = useState(null);
  const dec = state?.latest?.decision;
  const nodes = state?.latest?.nodes || {};
  const act = async (p, b) => { try { await api(p, b ?? {}); await refresh(); } catch (e) { toast(e.message, true); } };
  const load = async (id) => { await act("/api/replay/load", { event_id: id }); setPicked(null); setNodeHist(null); };
  useEffect(() => { if (!picked) return; let alive = true;
    const run = () => api(`/api/replay/node/${picked}`).then(d => alive && setNodeHist(d)).catch(() => {});
    run(); const id = setInterval(run, 2500); return () => { alive = false; clearInterval(id); }; }, [picked, state?.event_id]);
  const labels = useMemo(() => ticks.map(t => fmtT(t.t)), [ticks]);
  const S = (key) => ticks.map(t => t[key]);
  const M = (ch) => ticks.map(t => t.mean?.[ch] ?? null);
  const span = state?.window_start ? (new Date(state.window_end) - new Date(state.window_start)) : 1;
  const at = (iso) => iso && state?.window_start ? Math.max(0, Math.min(100, (new Date(iso) - new Date(state.window_start)) / span * 100)) : 0;
  const nodeLabel = (id) => facility?.nodes.find(n => n.id === id)?.label || id;
  const openCase = ctx.cases.find(c => c.status !== "CLOSED" && c.kind === "SENSOR_ALERT");

  return html`<div class="page">
    <div class="card"><h2>1 · Choose a recorded event to watch <span class="r"><${Info} k="replay"/></span></h2>
      <div class="events">${catalog.map(e => html`<button class=${`ev ${state?.event_id === e.id ? "on" : ""}`} onClick=${() => load(e.id)}>
        <div class="row between"><b>${e.id}</b><span class=${`pill ${e.truth === "fire" ? "CRITICAL" : "WATCH"}`}>${e.truth === "fire" ? "⚠ real fire" : "● work fumes"}</span></div>
        <small>${e.description}</small><small class="dim">${e.duration_min} min · recorded ${fmtT(e.start, true)}</small></button>`)}</div>
      <details style="margin-top:10px"><summary>About these recordings</summary><div class="muted" style="font-size:13px">Real sensor readings from staged fire and nuisance experiments in an industrial hall. Each event is analysed by an AI model trained without that event. Welding is a known limitation: there is only one welding recording, so the model never saw welding before.</div></details>
    </div>

    ${state?.event_id && html`<div class="card"><h2>2 · Replay <span class="r"><span class="pill rec">● Historical replay · ${fmtT(state.cursor, true)}</span></span></h2>
      <div class="row">
        ${state.running ? html`<button class="btn" onClick=${() => act("/api/replay/pause")}>❚❚ Pause</button>`
          : html`<button class="btn primary" disabled=${state.finished} onClick=${() => act("/api/replay/play")}>▶ ${state.progress > 0 ? "Continue" : "Start"}</button>`}
        <button class="btn" disabled=${state.running || state.finished} onClick=${() => act("/api/replay/step", { ticks: 6 })}>+1 minute</button>
        <span class="muted">Speed</span>
        <div class="seg">${(state.speeds || []).map(s => html`<button class=${state.speed === s ? "on" : ""} onClick=${() => act("/api/replay/speed", { speed: s })}>${s}×</button>`)}</div>
      </div>
      <div class="progress" style="margin-top:12px">
        <div class="evband" style=${`left:${at(state.event_start)}%;width:${at(state.event_end) - at(state.event_start)}%`}></div>
        <div class="fill" style=${`width:${state.progress * 100}%`}></div>
        <div class="lab"><span>${fmtT(state.window_start)}</span><span>event ${fmtT(state.event_start)}–${fmtT(state.event_end)}</span><span>${fmtT(state.window_end)}</span></div>
      </div>
      ${state.finished && html`<div class="muted" style="margin-top:8px">End of the recording (it stops before the next experiment).</div>`}
    </div>`}

    ${openCase && html`<div class="banner err" style="cursor:pointer" onClick=${() => location.hash = `#/cases/${openCase.id}`}>
      ⚠ <div><b>An incident follow-up is open. The replay paused so you can respond.</b> Open it, then come back and press Continue: ARGOS needs readings recorded after your intervention to check recovery.</div></div>`}

    ${state?.event_id && html`<${RiskBanner} decision=${dec}/>`}

    ${state?.event_id && html`<div class="grid g-main">
      <div class="card"><h2>3 · Equipment and sensors <span class="r muted">click a sensor for details</span></h2>
        <${HallMap} facility=${facility} nodes=${nodes} fireNodes=${dec?.fire_nodes} onPick=${setPicked} picked=${picked} showExits=${false}/>
        <div class="equip" style="margin-top:12px">${facility?.nodes.map(n => { const c = nodeCond(nodes[n.id], n.id, dec);
          return html`<button class="e" style="text-align:left;cursor:pointer" onClick=${() => setPicked(n.id)}><b>Sensor ${n.label}</b><span class=${`pill ${c[0]}`}>${c[1]}</span></button>`; })}</div>
      </div>
      <div class="card"><h2>AI fire likelihood <${Info} k="pfire"/></h2>
        <${LineChart} labels=${labels} height=${250} yMin=${0} yMax=${100} unit="%"
          series=${[{ label: "Fire likelihood (%) – highest sensor", data: S("max_p_fire").map(v => v == null ? null : v * 100), color: "#B3261E", fill: "rgba(179,38,30,.07)" },
                    { label: "Work fumes likelihood (%)", data: S("max_p_nuisance").map(v => v == null ? null : v * 100), color: "#2F5F98" }]}
          thresholds=${[{ label: "Alarm level (95 %)", value: 95, color: "#88715F" }]}/>
        <div class="muted" style="font-size:12.5px;margin-top:6px">An alarm needs two sensors above the alarm level for 30 seconds.</div>
      </div>
    </div>`}

    ${state?.event_id && html`<details class="card"><summary>Detailed measurements (for technical staff)</summary>
      <div class="grid g2">
        <div><div class="muted" style="font-size:13px">Carbon monoxide · ppm (average of reporting sensors)</div><${LineChart} labels=${labels} height=${160} unit="ppm" series=${[{ label: "CO (ppm)", data: M("co_ppm"), color: "#9A5B00" }]}/></div>
        <div><div class="muted" style="font-size:13px">Particles · count</div><${LineChart} labels=${labels} height=${160} series=${[{ label: "particles (count)", data: M("pm_total"), color: "#6A5677" }]}/></div>
        <div><div class="muted" style="font-size:13px">Volatile organic compounds · raw sensor value</div><${LineChart} labels=${labels} height=${160} series=${[{ label: "VOC (raw)", data: M("voc_raw"), color: "#3D8B7D" }]}/></div>
        <div><div class="muted" style="font-size:13px">Air temperature · °C</div><${LineChart} labels=${labels} height=${160} unit="°C" series=${[{ label: "temperature (°C)", data: M("temperature_c"), color: "#88715F" }]}/></div>
      </div>
      <table class="t" style="margin-top:12px"><thead><tr><th>Sensor</th><th class="num">Fire likelihood</th><th class="num">Work fumes</th><th class="num">CO (ppm)</th><th class="num">Particles</th></tr></thead>
        <tbody>${facility?.nodes.map(n => { const s = nodes[n.id];
          return html`<tr class="click" onClick=${() => setPicked(n.id)}><td><b>${n.label}</b> <span class="dim">${n.id}</span></td><td class="num">${pct(s?.p_fire)}</td><td class="num">${pct(s?.p_nuisance)}</td>
            <td class="num">${num(s?.readings?.co_ppm, 2)}</td><td class="num">${num(s?.readings?.pm_total, 0)}</td></tr>`; })}</tbody></table>
      <div class="muted mono" style="margin-top:8px">model ${state.model}</div>
    </details>`}

    ${picked && nodeHist && html`<div class="card"><h2>Sensor ${nodeLabel(picked)} <span class="r"><button class="btn sm ghost" onClick=${() => { setPicked(null); setNodeHist(null); }}>Close ✕</button></span></h2>
      <div class="muted" style="margin-bottom:8px">${nodeHist.points.length} readings up to now (one every 10 s).</div>
      <div class="grid g2">
        <${LineChart} labels=${nodeHist.points.map(p => fmtT(p.t))} yMin=${0} yMax=${100} unit="%" series=${[
          { label: "Fire likelihood (%)", data: nodeHist.points.map(p => p.p_fire == null ? null : p.p_fire * 100), color: "#B3261E" }, { label: "Work fumes (%)", data: nodeHist.points.map(p => p.p_nuisance == null ? null : p.p_nuisance * 100), color: "#2F5F98" }]}/>
        <${LineChart} labels=${nodeHist.points.map(p => fmtT(p.t))} series=${[
          { label: "CO (ppm)", data: nodeHist.points.map(p => p.co_ppm), color: "#9A5B00" }, { label: "VOC (raw)", data: nodeHist.points.map(p => p.voc_raw), color: "#3D8B7D" }]}/>
      </div></div>`}
  </div>`;
}

const STEPS_SENSOR = [
  ["Problem detected", "ARGOS sensors"], ["Inspection", "Drone (simulated)"], ["Intervention", "Technician"],
  ["Independent check", "Another authorized person"], ["Recovery check", "ARGOS, live sensor readings"], ["Completed", "—"],
];
const STEPS_FINDING = [
  ["Problem found", "Drone patrol (illustrative)"], ["Follow-up opened", "Operator"], ["Intervention", "Technician"],
  ["Independent check", "Another authorized person"], ["Follow-up inspection", "Drone (simulated)"], ["Completed", "—"],
];

function nowText(c, isFinding, missions) {
  if (c.status === "CLOSED") return isFinding ? "✓ Completed. The work was checked by a second person and a follow-up drone inspection (simulated) confirmed the problem is gone."
    : "✓ Completed. The work was checked by a second person and the sensors confirmed the hall is back to normal.";
  if (c.status === "OPEN") {
    const waiting = missions.find(m => m.status === "AWAITING_APPROVAL");
    if (waiting) return "A drone inspection is ready. Next: the operator approves the flight. Then the technician inspects the area and records the intervention.";
    return "Next: the technician inspects the area, fixes the problem and records the intervention below.";
  }
  if (c.status === "ACTION_RECORDED") return `The technician ${c.technician} recorded the intervention. Next: waiting for another authorized person to check the work. The technician cannot approve their own work.`;
  if (c.status === "VERIFIED") {
    if (isFinding) return "The work was checked. Next: send a follow-up drone inspection, mark the spot clear, then confirm the follow-up.";
    if (c.stabilization && !c.stabilization.passed) return c.stabilization.non_live_ticks_after_action > 0
      ? "We cannot confirm that the equipment is back to normal: after the intervention, the sensors repeated old values instead of sending live readings. The incident stays open."
      : "We cannot confirm recovery yet: not enough normal live readings since the intervention. Continue monitoring, then check again.";
    return "The work was checked. Next: ARGOS checks that the sensors are back to normal for 15 minutes of live readings.";
  }
  return "";
}


// ------------------------------------------------------------------ firefighter emergency pack
function PackCard({ c, toast }) {
  const [v, setV] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setV(await api(`/api/cases/${c.id}/pack`)); } catch (e) { setV(null); } }, [c.id]);
  usePoll(load, 5000, [c.id, c.severity, c.escalations]);
  if (!v || !v.eligible) return null;
  const run = async (path) => { setBusy(true); try { setV(await api(`/api/cases/${c.id}/pack/${path}`, {})); } catch (e) { toast(e.message, true); } setBusy(false); };
  const active = v.state === "ACTIVE";
  return html`<div class="card packcard" id="firepack">
    <div class="packhead"><div><div class="packtitle">✚ Firefighter Emergency Pack</div>
      <div class="muted">Issued ${v.auto ? "automatically" : "by the operator"} because this fire incident reached CRITICAL. Scan to open the responder briefing.</div></div>
      <span class="pill bad">DEMO ACCESS · fictional factory data</span></div>
    <div class="packbody">
      <div class="qrbox">${active ? html`<img src=${`/api/cases/${c.id}/pack/qr.png?g=${v.generation}`} alt=${`QR code for the firefighter briefing of incident ${c.id}`} width="200" height="200"/>`
        : html`<div class="qrnone">${v.state === "REVOKED" ? "Link revoked" : v.state === "EXPIRED" ? "Link expired" : "No link"}</div>`}</div>
      <div class="stack" style="flex:1;min-width:0">
        <div class="row">
          <a class=${`btn primary ${active ? "" : "disabled"}`} href=${v.local_url || "#"} target="_blank" rel="noopener">🚒 Firefighter Emergency Pack</a>
          <a class=${`btn ${active ? "" : "disabled"}`} href=${`/api/cases/${c.id}/pack/qr.png?g=${v.generation}`} download=${`ARGOS_QR_${c.id}.png`}>⬇ QR code</a>
          <a class="btn" href=${`/api/cases/${c.id}/pack/briefing.pdf`} download=${`ARGOS_firefighter_briefing_${c.id}.pdf`}>⬇ Briefing PDF</a>
        </div>
        <dl class="kv">
          <dt>Status</dt><dd><span class=${`pill ${active ? "ok" : "pending"}`}>${active ? "✓ link active" : v.state.toLowerCase()}</span>${v.opened ? html` <span class="muted">opened by a responder ${fmtWall(v.opened)}</span>` : ""}</dd>
          <dt>Expires</dt><dd>${fmtWall(v.expires_at)} <span class="muted">(short-lived, incident-specific, revocable)</span></dd>
          <dt>QR link</dt><dd class="hash">${v.qr_url || "—"}</dd>
        </dl>
        <div class="muted" style="font-size:12.5px">The QR code contains only this link, not the incident data. ${v.network_note}</div>
        ${v.lan_hint && html`<div class="muted" style="font-size:12.5px">ⓘ ${v.lan_hint}</div>`}
        <div class="row"><button class="btn sm" disabled=${busy} onClick=${() => run("issue")}>Issue new link</button>
          <button class="btn sm danger" disabled=${busy || !active} onClick=${() => run("revoke")}>Revoke link</button>
          <span class="muted" style="font-size:12px">ARGOS never contacts emergency services by itself. Not an approved emergency response plan.</span></div>
      </div>
    </div>
  </div>`;
}

function CaseDetail({ id, ctx }) {
  const { role, names, toast, refresh, drone, refreshDrone } = ctx;
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);
  const [trail, setTrail] = useState([]);
  const [action, setAction] = useState("");
  const [note, setNote] = useState("");
  const load = useCallback(async () => {
    try {
      const [cc, tl] = await Promise.all([api(`/api/cases/${id}`), api(`/api/timeline?case_id=${id}`)]);
      setC(cc); setTrail(tl); setErr(null);
    } catch (e) { setErr(e.message); }
  }, [id]);
  usePoll(load, 2000, [id]);
  if (err && !c) return html`<div class="page"><div class="banner err">This case could not be loaded (${err}). It may have been removed by a demo reset. <a href="#/cases">Back to Safety Cases</a></div></div>`;
  if (!c) return html`<div class="page"><div class="empty">Loading case…</div></div>`;
  const post = async (path, body) => { try { setC(await api(`/api/cases/${id}/${path}`, body ?? {})); await load(); await refresh(); await refreshDrone(); } catch (e) { toast(e.message, true); } };
  const isFinding = c.kind === "INSPECTION_FINDING";
  const missions = (drone?.missions || []).filter(m => (c.missions || []).includes(m.id));
  const followOk = missions.some(m => m.mode === "FOLLOW_UP" && m.status === "COMPLETED");
  const targetedDone = missions.some(m => m.mode === "TARGETED" && m.status === "COMPLETED");
  const done = isFinding
    ? [true, true, !!c.action, !!c.verification?.approved, followOk, c.status === "CLOSED"]
    : [true, targetedDone || !!c.action, !!c.action, !!c.verification?.approved, c.status === "CLOSED", c.status === "CLOSED"];
  const steps = isFinding ? STEPS_FINDING : STEPS_SENSOR;
  const cur = done.indexOf(false);
  const ev = c.evidence?.nodes || {};
  const fnd = c.evidence?.finding;
  const activeM = missions.find(m => ["AWAITING_APPROVAL", "IN_FLIGHT", "PAUSED"].includes(m.status));
  const canRequest = c.status !== "CLOSED" && !activeM && (!isFinding || c.action);

  return html`<div class="page">
    <div class="row between">
      <div class="row"><a href="#/cases" class="btn sm ghost">← Incident follow-up</a><h2 style="margin:0;font-size:20px">${c.id}</h2>
        <span class=${`pill ${c.status}`}>${c.status.replaceAll("_", " ")}</span><span class=${`pill ${c.severity}`}>${c.severity}</span>
        <span class=${`pill ${isFinding ? "sim" : "rec"}`}>${isFinding ? "From a drone patrol · illustrative" : "From the sensors · real recorded data"}</span>
        ${c.escalations ? html`<span class="pill bad" title="The recorded fire signature was still present or came back after the corrective action was recorded">fire signal after action ×${c.escalations}</span>` : ""}</div>
      <span class="muted">${c.zone} · opened ${isFinding ? fmtWall(c.opened_wall_ts) : `at recorded time ${fmtT(c.opened_data_ts, true)} (${c.replay_event})`}</span>
    </div>
    <div class="steps">${steps.map(([t, w], i) => html`<div class=${`step ${done[i] ? "done" : i === cur ? "cur" : ""}`}>
      <div class="n">Step ${i + 1} · ${done[i] ? "done" : i === cur ? "now" : "later"}</div><b>${done[i] ? "✓ " : i === cur ? "→ " : ""}${t}</b><div class="who">${w}</div></div>`)}</div>
    <div class="card nowbox"><h2>Where we are</h2><div style="font-size:16px">${nowText(c, isFinding, missions)}</div></div>
    ${!isFinding && html`<${PackCard} c=${c} toast=${toast}/>`}

    <div class="grid g-main">
      <div class="stack">
        <div class="card"><h2>${isFinding ? "What the drone patrol reported" : "What ARGOS detected"}</h2>
          <ul style="margin:0 0 10px;padding-left:18px">${c.findings.map(f => html`<li>${plainReason(f)}</li>`)}</ul>
          ${isFinding && fnd && html`<dl class="kv"><dt>Checkpoint</dt><dd>${fnd.checkpoint_label}</dd><dt>Type</dt><dd>${fnd.type_label}</dd>
            <dt>Severity</dt><dd>${fnd.severity}</dd><dt>Mission</dt><dd>${fnd.mission_id} (simulated)</dd><dt>Recorded by</dt><dd>${fnd.recorded_by} · ${fmtWall(fnd.recorded_at)}</dd></dl>
            <div class="banner sim" style="margin-top:10px">${fnd.label}</div>`}
          ${!isFinding && html`<details open><summary class="muted" style="cursor:pointer">Sensor readings when the problem was detected <${Info} k="pfire"/></summary>
            <table class="t"><thead><tr><th>Sensor</th><th class="num">Fire likelihood</th><th class="num">Nuisance likelihood</th><th class="num">CO (ppm)</th><th class="num">CO₂ (ppm)</th><th class="num">Particles</th><th class="num">Temp (°C)</th></tr></thead>
            <tbody>${Object.entries(ev).sort((a, b) => b[1].p_fire - a[1].p_fire).map(([k, v]) => html`<tr>
              <td>${ctx.facility?.nodes.find(n => n.id === k)?.label || k} ${c.fire_nodes.includes(k) && html`<span class="pill CRITICAL">fire signal</span>`}</td>
              <td class="num">${pct(v.p_fire)}</td><td class="num">${pct(v.p_nuisance)}</td><td class="num">${num(v.readings.co_ppm, 2)}</td>
              <td class="num">${num(v.readings.co2_ppm, 0)}</td><td class="num">${num(v.readings.pm_total, 0)}</td><td class="num">${num(v.readings.temperature_c, 1)}</td></tr>`)}</tbody></table>
            <div class="muted" style="margin-top:8px;font-size:12px">Recorded readings and held-out model outputs (model ${c.evidence?.model}). Historical replay of real data.</div></details>`}
        </div>
        <div class="card"><h2>What to do</h2><div>${c.recommended_inspection}</div>
          <div class="banner info" style="margin-top:10px">If you see flames or heavy smoke, follow the site emergency procedure. Certified fire alarms work independently of ARGOS.</div></div>

        <div class="card"><h2>Drone inspection <span class="r"><span class="pill sim">simulated drone</span></span></h2>
          ${missions.length ? html`<table class="t"><tbody>${missions.map(m => html`<tr><td><b>${m.id}</b> · ${MODE_LABEL[m.mode]}<div class="muted">${m.checkpoints.map(x => `${x.label}${x.result ? ` (${x.result})` : ""}`).join(", ")}</div></td>
            <td><span class=${`pill ${m.status === "COMPLETED" ? "ok" : m.status === "AWAITING_APPROVAL" ? "HIGH" : m.status === "CANCELLED" ? "pending" : "WATCH"}`}>${m.status.replace("_", " ")}</span></td>
            <td class="num">${m.status === "AWAITING_APPROVAL" ? html`<button class="btn sm primary" onClick=${async () => { try { await api(`/api/drone/missions/${m.id}/actions/approve`, {}); await refreshDrone(); } catch (e) { toast(e.message, true); } }}>Approve drone flight</button>`
              : m.status === "COMPLETED" ? html`${m.checkpoints.filter(x => !x.result).map(x => html`<button class="btn sm" onClick=${async () => { try { await api(`/api/drone/missions/${m.id}/clear`, { checkpoint: x.id }); await refreshDrone(); } catch (e) { toast(e.message, true); } }}>Mark ${x.label.split(" (")[0]} clear</button> `)}` : html`<a class="btn sm" href="#/drone">Watch →</a>`}</td></tr>`)}</tbody></table>`
            : html`<div class="empty">No inspection linked yet.</div>`}
          ${canRequest && html`<button class="btn" style="margin-top:8px" onClick=${() => post("inspection")}>${isFinding || c.action ? "Send follow-up inspection" : "Start inspection"}</button>`}
          ${isFinding && !c.action && html`<div class="muted" style="margin-top:6px">The follow-up inspection becomes available after the corrective action.</div>`}
          <div class="muted" style="margin-top:8px;font-size:12px">No physical drone, imagery or thermal data. Inspection results are recorded by the operator.</div>
        </div>
      </div>

      <div class="stack">
        <div class="card"><h2>1 · Intervention <span class="r muted">technician</span></h2>
          ${c.action ? html`<div><b>${c.technician}</b> <span class="muted">· ${fmtWall(c.action.wall_ts)}${c.action.data_ts ? ` (replay time ${fmtT(c.action.data_ts)})` : ""}</span><p>${c.action.text}</p></div>`
            : role !== "technician" ? html`<div class="muted">To record the intervention, choose the role <b>Technician</b> at the top right.</div>`
            : html`<div class="stack"><div class="muted">Acting as <b>${names.technician}</b></div>
                <textarea placeholder=${isFinding ? "What was done (e.g. pallets removed from the exit, area marked)" : "What was found and done (e.g. isolated the cable-tray circuit, removed burnt insulation)"} value=${action} onInput=${e => setAction(e.target.value)}></textarea>
                <button class="btn primary" disabled=${action.trim().length < 10 || c.status !== "OPEN"} onClick=${() => post("action", { technician: names.technician, action })}>Record intervention</button></div>`}
        </div>
        <div class="card"><h2>2 · Independent check <span class="r muted">another authorized person</span></h2>
          ${c.verification?.approved ? html`<div><b>${c.verifier}</b> <span class="muted">approved · ${fmtWall(c.verification.wall_ts)}</span><p>${c.verification.note || "—"}</p></div>`
            : c.status !== "ACTION_RECORDED" ? html`<div class="muted">Available after the technician records the intervention.${c.verification && !c.verification.approved ? html`<br/>Last verification was rejected by ${c.verification.by}: ${c.verification.note}` : ""}</div>`
            : role !== "verifier" ? html`<div class="muted">Waiting for another authorized person to check the work. Choose the role <b>Verifier</b> at the top right. The technician cannot approve their own work.</div>`
            : html`<div class="stack"><div class="muted">Acting as <b>${names.verifier}</b></div>
                <textarea placeholder="Verification note" value=${note} onInput=${e => setNote(e.target.value)}></textarea>
                <div class="row"><button class="btn primary" onClick=${() => post("verify", { verifier: names.verifier, approve: true, note })}>✓ Verify intervention</button>
                <button class="btn danger" onClick=${() => post("verify", { verifier: names.verifier, approve: false, note: note || "Rejected" })}>Reject</button></div></div>`}
        </div>
        <div class="card"><h2>3 · ${isFinding ? "Confirm with a follow-up inspection" : "Recovery check"} <span class="r muted">${isFinding ? "drone (simulated)" : "ARGOS, live readings"}</span></h2>
          <div class="muted" style="font-size:12.5px">${c.stabilization?.criterion || (isFinding
            ? "A follow-up drone inspection of the same checkpoint, flown after the corrective action, must confirm the condition is cleared."
            : "15 consecutive minutes of LIVE readings (at least 2 nodes) with risk NORMAL and fire likelihood < 20 %, after the corrective action. Gaps and held/repeated values do not count. Prototype rule, not a validated industrial standard.")}</div>
          ${c.stabilization && html`<div class="row" style="margin-top:10px"><span class=${`pill ${c.stabilization.passed ? "ok" : "bad"}`}>${c.stabilization.passed ? "✓ Confirmed" : "? Not confirmed yet"}</span>
            ${!isFinding && html`<span>${c.stabilization.measured_minutes} / ${c.stabilization.required_minutes} min of live normal readings</span><span class="muted">checked up to ${fmtT(c.stabilization.checked_up_to)}</span>`}</div>
            ${c.stabilization.note && html`<div class="muted" style="margin-top:6px;font-size:12.5px">${c.stabilization.note}</div>`}`}
          ${c.status === "VERIFIED" && html`<div class="row" style="margin-top:10px"><button class="btn primary" onClick=${() => post("close-check")}>${isFinding ? "Confirm follow-up" : "Check recovery"}</button></div>`}
          ${c.status === "CLOSED" && html`<div class="banner info" style="margin-top:10px">✓ Closed with 3 confirmations: technician, independent verifier, and ${isFinding ? "a follow-up inspection (simulated evidence)" : "live measured readings"}.</div>`}
          ${!isFinding && c.stabilization && !c.stabilization.passed && c.stabilization.non_live_ticks_after_action > 0 && html`<div class="banner info" style="margin-top:10px">ⓘ Why the case stays open: in this dataset the recording repeats its last values for 20–45 min after each experiment (likely the ventilation phase), and the next experiment starts soon after. Repeated values are not measurements, so ARGOS refuses to close the case on data it cannot trust.</div>`}
        </div>
        <${OutcomeCard} c=${c} ctx=${ctx} post=${post}/>
        <div class="card"><h2>Activity</h2><${Timeline} events=${trail} compact/></div>
      </div>
    </div>
  </div>`;
}

function SimBanner() {
  return html`<div class="banner sim">◈ <div><b>Simulated drone.</b> No real drone, camera or thermal sensor is connected, and no image-recognition model is used. Findings are entered by the operator and marked illustrative.</div></div>`;
}

function DroneOps({ ctx }) {
  const { drone, toast, refreshDrone } = ctx;
  const [route, setRoute] = useState("R-FULL");
  const [form, setForm] = useState(null);   // {mission, checkpoint}
  const [ftype, setFtype] = useState("obstructed_exit");
  const [sev, setSev] = useState("MEDIUM");
  const [note, setNote] = useState("");
  if (!drone) return html`<div class="page"><div class="empty">Loading drone operations…</div></div>`;
  const call = async (path, body) => { try { const r = await api(path, body ?? {}); await refreshDrone(); return r; } catch (e) { toast(e.message, true); } };
  const active = drone.active;
  const awaiting = drone.missions.filter(m => m.status === "AWAITING_APPROVAL");
  const rl = (id) => drone.routes.find(r => r.id === id)?.label || id;
  const freqs = [5, 15, 30, 60, 240, 1440];
  const [tab, setTab] = useState(awaiting.length ? "alert" : "routine");
  const isRoutine = (m) => m.mode === "PREVENTIVE";
  const shown = (active && (tab === "routine") === isRoutine(active) ? active : null) || drone.missions.find(m => (tab === "routine") === isRoutine(m) && m.status === "COMPLETED");
  const alertMissions = drone.missions.filter(m => !isRoutine(m));

  return html`<div class="page">
    <${SimBanner}/>
    <div class="tabs">
      <button class=${tab === "routine" ? "on" : ""} onClick=${() => setTab("routine")}>Routine inspections<small>Regular checks before any problem</small></button>
      <button class=${tab === "alert" ? "on" : ""} onClick=${() => setTab("alert")}>Alert inspections ${awaiting.length ? html`<span class="pill HIGH">${awaiting.length} to approve</span>` : ""}<small>Checking a specific warning</small></button>
    </div>
    ${tab === "alert" && html`<div class="card"><h2>Alert inspections</h2>
      ${alertMissions.length ? html`<table class="t"><thead><tr><th>Why</th><th>Where</th><th>Status</th><th></th></tr></thead><tbody>
        ${alertMissions.map(m => html`<tr><td><b>${MODE_LABEL[m.mode]}</b><div class="muted">${ORIGIN_LABEL[m.origin]}${m.case_id ? html` · <a href=${`#/cases/${m.case_id}`}>incident ${m.case_id}</a>` : ""}</div></td>
          <td>${m.checkpoints.map(c => c.label).join(", ")}</td>
          <td><span class=${`pill ${m.status === "COMPLETED" ? "ok" : m.status === "AWAITING_APPROVAL" ? "HIGH" : m.status === "CANCELLED" ? "pending" : "WATCH"}`}>${{ AWAITING_APPROVAL: "▲ waiting for approval", IN_FLIGHT: "● flying", PAUSED: "paused", COMPLETED: "✓ finished", CANCELLED: "cancelled" }[m.status]}</span></td>
          <td class="num">${m.status === "AWAITING_APPROVAL" && html`<button class="btn sm primary" disabled=${!!active} onClick=${() => call(`/api/drone/missions/${m.id}/actions/approve`)}>Approve drone flight</button>`}</td></tr>`)}</tbody></table>`
        : html`<div class="empty">No alert inspection. ARGOS asks for one automatically when the sensors confirm a fire signal.</div>`}</div>`}
    <div class="grid g-main">
      <div class="card"><h2>Hall map · route and drone position <span class="r muted">${active ? `${MODE_LABEL[active.mode]} in progress` : "drone on dock"}</span></h2>
        <${HallMap} facility=${ctx.facility} nodes=${ctx.state?.latest?.nodes || {}} fireNodes=${ctx.state?.latest?.decision?.fire_nodes} drone=${drone} mission=${shown}/>
      </div>
      <div class="stack">
        ${tab === "routine" && html`<div class="card"><h2>Start a routine inspection</h2>
          <div class="stack"><select class="in" value=${route} onChange=${e => setRoute(e.target.value)}>
            ${drone.routes.map(r => html`<option value=${r.id}>${r.label} (${r.checkpoints.length} checkpoints)</option>`)}</select>
            <button class="btn primary" disabled=${!!active} onClick=${() => call("/api/drone/missions", { route_id: route })}>▶ Start inspection now</button>
            ${active && html`<div class="muted">The drone is already flying. Pause or stop it to start another inspection.</div>`}</div></div>`}
        ${active && html`<div class="card"><h2>Mission ${active.id} <span class="r"><span class=${`pill ${active.status === "PAUSED" ? "HIGH" : "WATCH"}`}>${active.status.replace("_", " ")}</span></span></h2>
          <div><b>${MODE_LABEL[active.mode]}</b> · ${active.label} · <span class="muted">${ORIGIN_LABEL[active.origin]}</span></div>
          <div class="bar"><i style=${`width:${Math.round(active.progress * 100)}%`}></i></div>
          <div class="muted">${active.current || "Taking off"} · ${Math.round(active.progress * 100)} %</div>
          <div class="row" style="margin-top:8px">${active.status === "PAUSED"
            ? html`<button class="btn" onClick=${() => call(`/api/drone/missions/${active.id}/actions/resume`)}>▶ Resume</button>`
            : html`<button class="btn" onClick=${() => call(`/api/drone/missions/${active.id}/actions/pause`)}>❚❚ Pause</button>`}
            <button class="btn danger" onClick=${() => call(`/api/drone/missions/${active.id}/actions/cancel`)}>■ Stop inspection</button></div></div>`}
        ${tab === "routine" && awaiting.length > 0 && html`<div class="card" style="border-color:var(--high)"><h2>Waiting for your approval</h2>
          ${awaiting.map(m => html`<div class="stack" style="margin-bottom:8px"><div><b>${MODE_LABEL[m.mode]}</b> for <a href=${`#/cases/${m.case_id}`}>${m.case_id}</a></div>
            <div class="muted">${m.reason}</div><div class="muted">Checkpoints: ${m.checkpoints.map(c => c.label).join(", ")}</div>
            <div class="row"><button class="btn primary" disabled=${!!active} onClick=${() => call(`/api/drone/missions/${m.id}/actions/approve`)}>Approve flight</button>
            <button class="btn ghost" onClick=${() => call(`/api/drone/missions/${m.id}/actions/cancel`)}>Decline</button></div></div>`)}</div>`}
      </div>
    </div>

    ${shown && html`<div class="card"><h2>Checkpoints · mission ${shown.id} <span class="r muted">${shown.status === "COMPLETED" ? "completed" : "in progress"}</span></h2>
      <table class="t"><thead><tr><th>Checkpoint</th><th>What is checked</th><th>Status</th><th>Result (operator)</th><th></th></tr></thead><tbody>
      ${shown.checkpoints.map(c => { const cp = drone.checkpoints.find(x => x.id === c.id);
        return html`<tr><td><b>${c.label}</b></td><td class="muted">${cp?.checks.join(", ")}</td>
          <td>${c.status === "inspected" ? html`<span class="pill ok">inspected</span>` : html`<span class="pill pending">pending</span>`}</td>
          <td>${c.result === "finding" ? html`<span class="pill HIGH">finding recorded</span>` : c.result === "clear" ? html`<span class="pill ok">clear</span>` : "—"}</td>
          <td class="num">${c.status === "inspected" && !c.result && html`<div class="row" style="justify-content:flex-end">
            <button class="btn sm" onClick=${() => call(`/api/drone/missions/${shown.id}/clear`, { checkpoint: c.id })}>Mark clear</button>
            <button class="btn sm" onClick=${() => { setForm({ mission: shown.id, checkpoint: c.id, label: c.label }); setNote(""); }}>Record finding</button></div>`}</td></tr>`; })}
      </tbody></table>
      ${form && html`<div class="card" style="margin-top:12px;background:var(--bg2)"><h2>What did you see at ${form.label}? <span class="r"><span class="pill sim">illustrative</span></span></h2>
        <div class="grid g3"><label class="f">Type<select class="in" value=${ftype} onChange=${e => setFtype(e.target.value)}>
          ${Object.entries(drone.finding_types).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select></label>
          <label class="f">Severity<select class="in" value=${sev} onChange=${e => setSev(e.target.value)}>${drone.severities.map(s => html`<option>${s}</option>`)}</select></label>
          <label class="f">Note<input type="text" value=${note} onInput=${e => setNote(e.target.value)} placeholder="What the inspector would see"/></label></div>
        <div class="row" style="margin-top:10px"><button class="btn primary" onClick=${async () => { const r = await call(`/api/drone/missions/${form.mission}/findings`, { checkpoint: form.checkpoint, type: ftype, severity: sev, note }); if (r) setForm(null); }}>Save finding</button>
          <button class="btn ghost" onClick=${() => setForm(null)}>Cancel</button>
          <span class="muted">Recorded by the operator from a simulated mission. Not an automatic detection.</span></div></div>`}
    </div>`}

    ${tab === "routine" && html`<div class="grid g2">
      <div class="card"><h2>Routine patrol plan <span class="r"><span class="pill sim">SIMULATED SCHEDULER</span></span></h2>
        <div class="muted" style="font-size:12.5px;margin-bottom:8px">${drone.scheduler_note}</div>
        <table class="t"><thead><tr><th>Route</th><th>Every</th><th>Next patrol</th><th>Active</th></tr></thead><tbody>
          ${drone.schedules.map(s => html`<tr><td><b>${rl(s.route_id)}</b></td>
            <td><select class="in" style="width:auto;padding:4px 8px" value=${s.every_minutes} onChange=${e => call(`/api/drone/schedules/${s.id}`, { every_minutes: +e.target.value })}>
              ${[...new Set([...freqs, s.every_minutes])].sort((a, b) => a - b).map(f => html`<option value=${f}>${f < 60 ? `${f} min` : f === 1440 ? "24 h" : `${f / 60} h`}</option>`)}</select></td>
            <td>${s.enabled ? inMin(s.next_due) : "—"} <button class="btn sm ghost" onClick=${() => call(`/api/drone/schedules/${s.id}`, { start_in_minutes: 1 })}>in 1 min</button></td>
            <td><button class=${`btn sm ${s.enabled ? "" : "ghost"}`} onClick=${() => call(`/api/drone/schedules/${s.id}`, { enabled: !s.enabled })}>${s.enabled ? "On" : "Off"}</button></td></tr>`)}</tbody></table></div>
      <div class="card"><h2>Findings <span class="r"><span class="pill sim">illustrative</span></span></h2>
        ${drone.findings.length ? html`<table class="t"><tbody>${drone.findings.map(f => html`<tr>
          <td><b>${f.type_label}</b><div class="muted">${f.checkpoint_label} · ${f.note || "—"}</div></td>
          <td><span class=${`pill ${f.severity === "HIGH" ? "CRITICAL" : f.severity === "MEDIUM" ? "HIGH" : "WATCH"}`}>${f.severity}</span></td>
          <td class="num">${f.case_id ? html`<a class="btn sm" href=${`#/cases/${f.case_id}`}>${f.case_id} →</a>`
            : html`<button class="btn sm primary" onClick=${async () => { const c = await call(`/api/findings/${f.id}/case`, { opened_by: "operator" }); if (c) location.hash = `#/cases/${c.id}`; }}>Open incident follow-up</button>`}</td></tr>`)}</tbody></table>`
          : html`<div class="empty">No finding yet. During an inspection, mark each checkpoint clear or record what you see.</div>`}</div>
    </div>`}

    <div class="card"><h2>Inspection history</h2>
      ${drone.missions.length ? html`<table class="t"><thead><tr><th>Mission</th><th>Type</th><th>Trigger</th><th>Checkpoints</th><th>Status</th><th>Findings</th><th>Case</th></tr></thead><tbody>
        ${drone.missions.map(m => html`<tr><td><b>${m.id}</b><div class="muted">${fmtWall(m.created_at)}</div></td><td>${MODE_LABEL[m.mode]}</td><td class="muted">${ORIGIN_LABEL[m.origin]}</td>
          <td class="muted">${m.checkpoints.map(c => c.label).join(" → ")}</td><td><span class=${`pill ${m.status === "COMPLETED" ? "ok" : m.status === "CANCELLED" ? "pending" : "WATCH"}`}>${m.status.replace("_", " ")}</span></td>
          <td class="num">${m.findings.length}</td><td>${m.case_id ? html`<a href=${`#/cases/${m.case_id}`}>${m.case_id}</a>` : "—"}</td></tr>`)}</tbody></table>`
        : html`<div class="empty">No mission flown yet.</div>`}</div>
  </div>`;
}

function Cases({ ctx }) {
  const { cases } = ctx;
  return html`<div class="page"><div class="card"><h2>Incident follow-up <span class="r muted">called Safety Cases in the documentation</span></h2>
    ${cases.length ? html`<table class="t"><thead><tr><th>Case</th><th>Status</th><th>Severity</th><th>Zone</th><th>Recorded time opened</th><th>Technician</th><th>Verifier</th></tr></thead>
      <tbody>${cases.map(c => html`<tr class="click" onClick=${() => location.hash = `#/cases/${c.id}`}>
        <td><b>${c.id}</b></td><td><span class=${`pill ${c.status}`}>${c.status.replace("_", " ")}</span></td><td><span class=${`pill ${c.severity}`}>${c.severity}</span></td>
        <td>${c.zone}</td><td class="mono">${fmtT(c.opened_data_ts, true)}</td><td>${c.technician || "—"}</td><td>${c.verifier || "—"}</td></tr>`)}</tbody></table>`
      : html`<div class="empty">No incident yet. An incident opens when two sensors agree on a fire, or when a drone finding needs action. Try the guided tour.</div>`}
  </div></div>`;
}

function Timeline({ events, compact }) {
  if (!events.length) return html`<div class="empty">No events recorded yet</div>`;
  const title = eventTitle;
  const detail = (e) => e.kind === "risk_level_changed" ? e.payload.reasons?.[0] : e.kind === "technician_action" ? e.payload.action
    : e.kind === "stabilization_check" ? `${e.payload.measured_minutes}/${e.payload.required_minutes} min measured normal` : e.kind === "alert" ? e.payload.reasons?.[0]
    : e.kind === "verification_approved" || e.kind === "verification_rejected" ? e.payload.note : "";
  return html`<div class="tl">${events.map(e => html`<div class="it">
    <div class="when">${e.data_ts ? html`${fmtT(e.data_ts)}<div class="dim">recorded time</div>` : html`${fmtWall(e.wall_ts)}<div class="dim">wall clock</div>`}</div>
    <div class=${`dot src-${e.source}`}></div>
    <div class="body"><b>${title(e)}</b> <span class=${`pill ${e.source === "simulated" ? "sim" : e.source === "human" ? "ok" : "pending"}`} style="font-size:10.5px">${SRC[e.source]}</span>
      ${e.actor && html` <span class="muted">· ${e.actor}</span>`}${!compact && e.case_id && html` <a href=${`#/cases/${e.case_id}`}>${e.case_id}</a>`}
      ${detail(e) && html`<div class="d">${detail(e)}</div>`}${!compact && html`<div class="hash">#${e.seq} · ${e.hash.slice(0, 20)}…</div>`}</div></div>`)}</div>`;
}

function BlackBox({ ctx }) {
  const [events, setEvents] = useState([]);
  const [src, setSrc] = useState(new Set(Object.keys(SRC)));
  usePoll(async () => setEvents(await api("/api/timeline?limit=800")), 2500, []);
  const shown = events.filter(e => src.has(e.source));
  const toggle = (k) => { const n = new Set(src); n.has(k) ? n.delete(k) : n.add(k); setSrc(n); };
  return html`<div class="page">
    <div class="banner info">ⓘ <div>The Black Box is generated from the persisted, hash-chained event log. <b>Recorded time</b> = timestamp of the real recording being replayed. Human actions are performed with <b>demo roles</b>; drone steps are a <b>simulated workflow</b>.</div></div>
    <div class="card"><h2>Incident timeline <span class="r">${shown.length} events</span></h2>
      <div class="row" style="margin-bottom:12px">${Object.entries(SRC).map(([k, v]) => html`<button class=${`btn sm ${src.has(k) ? "" : "ghost"}`} onClick=${() => toggle(k)}><span class=${`dot src-${k}`} style="width:10px;height:10px;border-radius:50%;display:inline-block"></span>${v}</button>`)}</div>
      <${Timeline} events=${shown}/>
    </div></div>`;
}

const HSTAT = { VERIFIED: ["ok", "✓ Verified on Hedera"], AWAITING_CONFIRMATION: ["HIGH", "… Awaiting confirmation"], SUBMITTED: ["HIGH", "… Submitted, not yet verified"],
  MISMATCH: ["bad", "⚠ Evidence mismatch"], UNAVAILABLE: ["pending", "? Hedera unavailable"], NOT_ANCHORED: ["pending", "○ Not anchored"], FAILED: ["bad", "⚠ Submission failed"], PENDING: ["pending", "○ Not anchored"] };

function HederaCard({ toast }) {
  const [h, setH] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = async () => setH(await api("/api/hedera"));
  usePoll(load, 5000, []);
  if (!h) return null;
  const run = async (fn) => { setBusy(true); try { await fn(); await load(); } catch (e) { toast(e.message, true); } setBusy(false); };
  const a = h.latest; const st = a ? (a.verification?.status || a.status) : "NOT_ANCHORED";
  return html`<div class="card"><h2>Hedera evidence <span class="r"><span class="pill rec">Hedera testnet</span></span></h2>
    <div class="muted" style="margin-bottom:12px">ARGOS stores a digital fingerprint of the incident history on Hedera, so any later change can be detected. Only the fingerprint is sent, never sensor data or names.</div>
    <div class="grid g2">
      <dl class="kv">
        <dt>Local evidence</dt><dd><span class=${`pill ${h.local_chain.ok ? "ok" : "bad"}`}>${h.local_chain.ok ? "✓ intact" : "⚠ broken"}</span> <span class="muted">${h.local_chain.events} events</span></dd>
        <dt>Hedera status</dt><dd><span class=${`pill ${HSTAT[st][0]}`}>${HSTAT[st][1]}</span></dd>
        <dt>Topic ID</dt><dd class="mono">${h.topic_id || "—"}</dd>
        <dt>Transaction ID</dt><dd class="mono">${a?.transaction_id || "—"}</dd>
        <dt>Consensus time</dt><dd class="mono">${a?.consensus_timestamp || "—"}</dd>
        <dt>Fingerprint</dt><dd class="hash">${a?.snapshot?.head_sha256 || "—"}</dd>
      </dl>
      <div class="stack">
        ${!h.configured && html`<div class="banner err">Not connected: ${h.config_message}. No transaction is shown until a real one exists.</div>`}
        <button class="btn primary" disabled=${busy || !h.configured} onClick=${() => run(() => api("/api/hedera/anchor", {}))}>Anchor evidence to Hedera</button>
        <button class="btn" disabled=${busy || !a?.sequence_number} onClick=${() => run(() => api(`/api/hedera/anchors/${a.id}/verify`, {}))}>Verify on Hedera</button>
        ${h.explorer && html`<a class="btn ghost" href=${h.explorer} target="_blank" rel="noopener">Open topic on HashScan ↗</a>`}
        ${a?.verification && html`<div class="muted" style="font-size:13px">${a.verification.detail} <span class="dim">(${a.verification.checked_at})</span></div>`}
        <div class="muted" style="font-size:12px">Hedera proves the fingerprint existed at a given time. It does not prove that sensor readings or labels are physically true.</div>
      </div>
    </div>
    ${h.anchors.length > 1 && html`<details style="margin-top:10px"><summary>All anchors (${h.anchors.length})</summary><table class="t"><tbody>${h.anchors.map(x => html`<tr>
      <td class="mono">${x.id}</td><td>${x.snapshot.evidence_type}</td><td class="mono">${x.transaction_id || "—"}</td><td><span class=${`pill ${HSTAT[x.verification?.status || x.status][0]}`}>${HSTAT[x.verification?.status || x.status][1]}</span></td></tr>`)}</tbody></table></details>`}
  </div>`;
}

function LearningCard({ toast }) {
  const [l, setL] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const load = async () => setL(await api("/api/learning"));
  usePoll(load, 6000, []);
  if (!l) return null;
  const run = async (fn) => { setBusy(true); setMsg(null); try { const r = await fn(); await load(); return r; } catch (e) { setMsg(e.message); } finally { setBusy(false); } };
  const m = l.current_model, d = l.datasets[0];
  return html`<div class="card"><h2>AI learning <span class="r"><span class="pill pending">advanced users</span></span></h2>
    <div class="muted" style="margin-bottom:12px">ARGOS can learn only from incidents whose real outcome was confirmed by a second person, whose evidence is intact and verified on Hedera, and that are genuinely new. It never replaces the approved model automatically.</div>
    <div class="grid g3">
      <div><div class="muted" style="font-size:12px">CURRENT MODEL</div><b>${m.available ? `${m.name} ${m.version}` : "not available"}</b>
        <div class="muted" style="font-size:13px">${m.status} · fires ${m.summary?.fires_detected}, nuisance alarms ${m.summary?.nuisance_alarms} (held-out)</div>
        <div class="hash">model ${m.model_sha256?.slice(0, 16)}… · data ${m.training_data_sha256?.slice(0, 16)}…</div></div>
      <div><div class="muted" style="font-size:12px">LEARNING DATA</div>
        <div><span class="pill ok">${l.counts.ELIGIBLE} eligible</span> <span class="pill HIGH">${l.counts.AWAITING_OUTCOME} awaiting outcome</span> <span class="pill pending">${l.counts.EXCLUDED} excluded</span></div></div>
      <div><div class="muted" style="font-size:12px">LATEST DATASET</div>${d ? html`<b>${d.id}</b> · ${d.new_examples} new example(s)<div class="hash">${d.sha256}</div>` : html`<span class="muted">none prepared</span>`}</div>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="btn" disabled=${busy} onClick=${() => run(() => api("/api/learning/dataset", {}))}>Prepare learning dataset</button>
      <button class="btn" disabled=${busy || !d} onClick=${async () => { const r = await run(() => api(`/api/learning/dataset/${d.id}/verify`, {})); if (r) setMsg(r.manifest_hash_ok ? `✓ Dataset ${d.id} unchanged since it was prepared.${r.anchored.length ? ` Anchored: ${r.anchored.join(", ")}.` : " Not yet anchored on Hedera."}` : "⚠ Dataset manifest was modified."); }}>Verify training evidence</button>
      <button class="btn" disabled=${busy || !d} onClick=${() => run(() => api(`/api/learning/dataset/${d.id}/anchor`, {}))}>Anchor dataset fingerprint</button>
      <button class="btn primary" disabled=${busy || !d} onClick=${() => run(() => api(`/api/learning/dataset/${d.id}/train`, {}))}>Train candidate model</button>
    </div>
    ${msg && html`<div class="banner info" style="margin-top:10px">${msg}</div>`}
    <div class="muted" style="font-size:12.5px;margin-top:8px">Model promotion: ${l.promotion}</div>
    <details style="margin-top:10px"><summary>Incidents and why they are (not) used</summary>
      ${l.incidents.length ? html`<table class="t"><thead><tr><th>Incident</th><th>Source</th><th>Outcome</th><th>Status</th><th>Reasons</th></tr></thead><tbody>
        ${l.incidents.map(r => html`<tr><td><a href=${`#/cases/${r.incident_id}`}>${r.incident_id}</a></td><td class="muted">${r.provenance}${r.recording ? ` · ${r.recording}` : ""}</td>
          <td>${r.outcome ? l.outcomes[r.outcome] : "—"}</td><td><span class=${`pill ${r.state === "ELIGIBLE" ? "ok" : r.state === "AWAITING_OUTCOME" ? "HIGH" : "pending"}`}>${r.state.replace("_", " ").toLowerCase()}</span></td>
          <td class="muted" style="font-size:12.5px">${r.reasons.join(" · ") || "—"}</td></tr>`)}</tbody></table>` : html`<div class="empty">No incident yet.</div>`}
    </details>
  </div>`;
}

function OutcomeCard({ c, ctx, post }) {
  const [o, setO] = useState("confirmed_fire");
  const [note, setNote] = useState("");
  const labels = { confirmed_fire: "It was a real fire", confirmed_nuisance: "Not a fire (work fumes or other nuisance)", confirmed_equipment_anomaly: "An equipment problem, no fire",
    confirmed_normal: "Everything was normal", inconclusive: "Not sure" };
  if (c.kind === "INSPECTION_FINDING") return null;
  if (c.outcome) return html`<div class="card"><h2>What really happened <span class="r muted">confirmed</span></h2><b>${labels[c.outcome.label]}</b>
    <div class="muted">Confirmed by ${c.outcome.by} · ${fmtWall(c.outcome.wall_ts)}${c.outcome.note ? ` · ${c.outcome.note}` : ""}</div></div>`;
  if (!["VERIFIED", "CLOSED"].includes(c.status)) return null;
  return html`<div class="card"><h2>What really happened? <span class="r muted">second person</span></h2>
    ${ctx.role !== "verifier" ? html`<div class="muted">After the check, another authorized person confirms what really happened. Choose the role <b>Verifier</b>. This helps ARGOS learn; the technician cannot confirm their own case.</div>`
      : html`<div class="stack"><select class="in" value=${o} onChange=${e => setO(e.target.value)}>${Object.entries(labels).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select>
        <input type="text" placeholder="What did you see? (optional)" value=${note} onInput=${e => setNote(e.target.value)}/>
        <button class="btn primary" onClick=${() => post("outcome", { person: ctx.names.verifier, outcome: o, note })}>Confirm what happened</button></div>`}
  </div>`;
}

function Passport({ ctx }) {
  const [p, setP] = useState(null);
  usePoll(async () => setP(await api("/api/passport")), 3000, []);
  if (!p) return html`<div class="page"><div class="empty">Loading…</div></div>`;
  return html`<div class="page">
    <div class="grid g3">
      <div class="card"><h2>Monitored zone</h2><dl class="kv">
        <dt>Identifier</dt><dd><b>${p.zone.id}</b></dd><dt>Name</dt><dd>${p.zone.name}</dd><dt>Site</dt><dd>${p.zone.site}</dd>
        <dt>Dimensions</dt><dd>${p.zone.dimensions_m.length} × ${p.zone.dimensions_m.width} × ${p.zone.dimensions_m.height} m</dd>
        <dt>Criticality</dt><dd>${p.zone.criticality} / 5</dd><dt>Sensors</dt><dd>${p.nodes.length} multi-gas nodes</dd></dl></div>
      <div class="card"><h2>Integrity</h2>
        <div class="row"><span class=${`pill ${p.integrity.ok ? "ok" : "bad"}`}>${p.integrity.ok ? "LOCAL CHAIN INTACT" : "CHAIN BROKEN"}</span><span class="muted">${p.integrity.events} events</span></div>
        <div class="hash" style="margin-top:8px">head ${p.integrity.head || "—"}</div>
        <div class="muted" style="font-size:12.5px;margin-top:8px">Blockchain fingerprint: see "Hedera evidence" below.</div></div>
      <div class="card"><h2>History</h2><div class="grid g3">
        <div class="kpi"><div class="v">${p.counts.total}</div><div class="l">cases</div></div>
        <div class="kpi"><div class="v" style="color:var(--ok)">${p.counts.closed}</div><div class="l">closed (3 confirmations)</div></div>
        <div class="kpi"><div class="v" style=${p.counts.open ? "color:var(--crit)" : ""}>${p.counts.open}</div><div class="l">open</div></div></div></div>
    </div>
    <div class="card"><h2>Safety Case history</h2>
      ${p.cases.length ? html`<table class="t"><thead><tr><th>Case</th><th>Status</th><th>Opened (recorded)</th><th>Corrective action</th><th>Verified by</th><th>Stabilization</th></tr></thead><tbody>
        ${p.cases.map(c => html`<tr class="click" onClick=${() => location.hash = `#/cases/${c.id}`}><td><b>${c.id}</b></td><td><span class=${`pill ${c.status}`}>${c.status.replace("_", " ")}</span></td>
          <td class="mono">${fmtT(c.opened_data_ts, true)}</td><td>${c.action ? html`${c.action.text}<div class="muted">${c.technician}</div>` : "—"}</td><td>${c.verifier || "—"}</td>
          <td>${c.stabilization ? `${c.stabilization.measured_minutes}/${c.stabilization.required_minutes} min ${c.stabilization.passed ? "✓" : ""}` : "—"}</td></tr>`)}</tbody></table>`
        : html`<div class="empty">No case in this zone yet</div>`}</div>
    <${HederaCard} toast=${ctx.toast}/>
    <div class="card"><h2>Drone inspection history <span class="r"><span class="pill sim">SIMULATED</span></span></h2>
      ${p.inspections?.missions?.length ? html`<table class="t"><thead><tr><th>Mission</th><th>Type</th><th>Checkpoints and results</th><th>Status</th><th>Case</th></tr></thead><tbody>
        ${p.inspections.missions.map(m => html`<tr><td><b>${m.id}</b><div class="muted">${fmtWall(m.created_at)}</div></td><td>${MODE_LABEL[m.mode]}<div class="muted">${ORIGIN_LABEL[m.origin]}</div></td>
          <td class="muted">${m.checkpoints.map(x => `${x.label}${x.result ? `: ${x.result}` : ""}`).join(" · ")}</td>
          <td><span class=${`pill ${m.status === "COMPLETED" ? "ok" : m.status === "CANCELLED" ? "pending" : "WATCH"}`}>${m.status.replace("_", " ")}</span></td>
          <td>${m.case_id ? html`<a href=${`#/cases/${m.case_id}`}>${m.case_id}</a>` : "—"}</td></tr>`)}</tbody></table>`
        : html`<div class="empty">No drone inspection yet.</div>`}</div>
    <div class="card"><h2>Model provenance <span class="r muted">which data produced which model</span></h2>
      <table class="t"><thead><tr><th>Model</th><th>Model file SHA-256</th><th>Training data SHA-256</th></tr></thead><tbody>
        ${p.models.map(m => html`<tr><td><b>${m.name}</b> <span class="muted">${m.version}</span></td><td class="hash">${m.model_sha256}</td><td class="hash">${m.training_data_sha256}</td></tr>`)}</tbody></table></div>
  </div>`;
}

function FirePack({ ctx }) {
  const [f, setF] = useState(null);
  usePoll(async () => setF(await api("/api/firepack")), 3000, []);
  if (!f) return html`<div class="page"><div class="empty">Loading…</div></div>`;
  const fac = f.facility, dec = f.latest?.decision, nodes = f.latest?.nodes || {};
  const flagged = Object.entries(nodes).filter(([k, v]) => dec?.fire_nodes?.includes(k) || v.p_fire >= 0.5);
  return html`<div class="page">
    <div class="row between noprint"><div class="banner info" style="flex:1">ⓘ Emergency reference for the Protection Civile. Layout, exits and contacts are <b>illustrative</b> for this demo site; readings come from the historical replay.</div>
      <button class="btn primary" onClick=${() => print()}>🖨 Print / save as PDF (offline copy)</button></div>
    <div class="card"><h2>EMERGENCY FIRE PACK · ${fac.name} <span class="r">${f.replay.event_id ? `replay ${f.replay.event_id} · recorded ${fmtT(f.replay.cursor, true)}` : "no replay loaded"}</span></h2>
      <div class="grid g-main">
        <div><${HallMap} facility=${fac} nodes=${nodes} fireNodes=${dec?.fire_nodes}/></div>
        <div class="stack">
          <div><b>Current zone status</b><div style="margin-top:6px"><span class=${`pill ${dec?.level || "NO_DATA"}`}>${LEVEL_TEXT[dec?.level || "NO_DATA"]}</span> <span class="muted">${dec?.reasons?.[0] || ""}</span></div></div>
          <div><b>Flagged sensor nodes</b>${flagged.length ? html`<ul style="margin:6px 0;padding-left:18px">${flagged.map(([k, v]) => html`<li>${fac.nodes.find(n => n.id === k)?.label}: P(fire) ${pct(v.p_fire)}, CO ${num(v.readings.co_ppm, 2)} ppm, particles ${num(v.readings.pm_total, 0)}</li>`)}</ul>` : html`<div class="muted">None</div>`}</div>
          <div><b>Exits</b><ul style="margin:6px 0;padding-left:18px">${fac.exits.map(e => html`<li>${e.label}</li>`)}</ul></div>
          <div><b>Hazardous materials</b><div class="muted">${fac.hazardous_materials.length ? "" : fac.hazardous_materials_note}</div></div>
          <div><b>Activities in the hall</b><div class="muted">${fac.activities.join(" · ")}</div></div>
          <div><b>Emergency contacts</b><table class="t"><tbody>${fac.emergency_contacts.map(c => html`<tr><td>${c.name}</td><td class="num"><b>${c.phone}</b></td></tr>`)}</tbody></table></div>
          ${f.open_cases.length > 0 && html`<div><b>Open incidents</b><div class="muted">${f.open_cases.map(c => html`<a href=${`#/cases/${c.id}`}>${c.id}</a> (${c.status.replaceAll("_", " ").toLowerCase()}${c.kind === "SENSOR_ALERT" && c.severity === "CRITICAL" ? ", firefighter QR pack available" : ""}) `)}</div></div>`}
        </div>
      </div></div></div>`;
}

function Evidence({ ctx }) {
  const [e, setE] = useState(null);
  useEffect(() => { api("/api/evidence").then(setE).catch(() => {}); }, []);
  if (!e) return html`<div class="page"><div class="empty">Loading…</div></div>`;
  const z = e.zone_nested || {}, b = e.zone_particle_baseline || {}, w = e.early_warning || {}, c = e.compressor?.Autoencoder || {}, t = e.timing;
  return html`<div class="page">
    <div class="card"><h2>What the evidence supports</h2>
      <table class="t"><thead><tr><th>Claim</th><th>Evidence (real data)</th><th>Status</th></tr></thead><tbody>
        <tr><td><b>Detects incipient fires in an industrial hall</b></td><td>Each event held out: AI <b>${z.fires_detected}/${z.fire_events}</b> fires, <b>${z.nuisance_false_alarms}/${z.nuisance_events}</b> nuisance alarms; a calibrated particle threshold does as well (${b.fires_detected}/${b.fire_events}, ${b.nuisance_false_alarms}/${b.nuisance_events}) with fewer background alarms</td><td><span class="pill ok">held-out, small sample</span></td></tr>
        <tr><td><b>Alarms earlier than a calibrated particle threshold</b></td><td>${t ? html`Earlier on <b>${t.ai_earlier}/${t.pairs}</b> fires detected by both, median <b>${Math.round(t.median_s)} s</b> earlier` : "see MODEL_REPORT"}</td><td><span class="pill ok">held-out, small sample</span></td></tr>
        <tr><td><b>Rejects nuisances better than a simple rule</b></td><td>Not shown on this data (AI ${z.nuisance_false_alarms}/${z.nuisance_events} vs particle rule ${b.nuisance_false_alarms}/${b.nuisance_events}); welding fools both</td><td><span class="pill bad">not demonstrated</span></td></tr>
        <tr><td><b>Warns earlier than a conventional smoke detector</b></td><td>Laboratory fires: earlier in ${w.warned_before_detector}/${w.experiments_scored}; electrical fires ${(w.electrical_lead_time_min || []).join(", ")} min earlier</td><td><span class="pill ok">laboratory, rule fixed in advance</span></td></tr>
        <tr><td><b>Detects equipment failures before they happen</b></td><td>Railway compressor (MetroPT-3): ${c.detected}/4 failures detected, ${c.detected_before_start} before the reported start; ~${c.false_alarms_per_week} false alarms/week</td><td><span class="pill HIGH">exploratory, secondary demo</span></td></tr>
        <tr><td><b>Prevents industrial fires</b></td><td>No dataset links detected anomalies to fires that were then avoided</td><td><span class="pill bad">not demonstrated</span></td></tr>
      </tbody></table>
      <div class="muted" style="margin-top:8px;font-size:12.5px">Full method, intervals and limitations: <a href="/reports/evaluation.md" target="_blank">ai/reports/evaluation.md</a>. Data provenance: docs/DATA_PROVENANCE_AUDIT.md.</div></div>
    <${LearningCard} toast=${ctx.toast}/>
    <div class="grid g2">
      <div class="card"><h2>AI vs calibrated particle threshold (Industrial Hall)</h2><img class="fig" src="/reports/zone_fire_vs_nuisance.png" alt="zone results"/></div>
      <div class="card"><h2>Earlier than the conventional detector (lab)</h2><img class="fig" src="/reports/lead_time.png" alt="lead time"/></div>
      <div class="card"><h2>Real cable fire vs welding (raw sensors)</h2><img class="fig" src="/figures/hall_cable_vs_welding.png" alt="cable vs welding"/></div>
      <div class="card"><h2>What starts industrial fires (ARIA, France)</h2><img class="fig" src="/figures/aria_fire_causes.png" alt="causes"/></div>
    </div></div>`;
}

// ------------------------------------------------------------------ app shell
// ------------------------------------------------------------------ guided demo
// Every "Do it" button calls the real API. Nothing here injects a prediction or a result.
const sensorCase = (ctx) => ctx.cases.filter(c => c.kind === "SENSOR_ALERT" && c.replay_event === "Cable#4")
  .sort((a, b) => b.opened_wall_ts.localeCompare(a.opened_wall_ts))[0];
const SCENARIOS = {
  patrol: {
    title: "Tour 1 · Routine drone inspection",
    tag: "SIMULATED DRONE · ILLUSTRATIVE FINDING",
    steps: [
      { title: "The preventive patrol plan", go: "#/drone",
        text: "ARGOS does not wait for an alarm. The drone flies predefined routes on a schedule (here: full patrol every hour). The scheduler is simulated and runs while the server runs." },
      { title: "Start a patrol", go: "#/drone", label: "Start the full patrol",
        act: async (ctx, d) => { const a = ctx.drone?.active; if (a && a.mode === "PREVENTIVE") return { mission: a.id };
          const m = await api("/api/drone/missions", { route_id: "R-FULL" }); return { mission: m.id }; },
        done: (ctx, d) => !!d.mission,
        text: "The operator launches the patrol manually (scheduled patrols use the same mission). Watch the drone leave its dock on the schematic." },
      { title: "Watch the route and checkpoints", go: "#/drone",
        done: (ctx, d) => ctx.drone?.missions.find(m => m.id === d.mission)?.checkpoints.find(c => c.id === "CP-EE")?.status === "inspected",
        text: "The drone visits each checkpoint: west exit, electrical cabinets, cable tray, welding bay, east exit, storage. Wait until the East loading door has been inspected." },
      { title: "Record an illustrative finding", go: "#/drone", label: "Record: exit obstructed",
        act: async (ctx, d) => { const f = await api(`/api/drone/missions/${d.mission}/findings`, { checkpoint: "CP-EE", type: "obstructed_exit", severity: "MEDIUM", note: "Illustrative: pallets stored in front of the east loading door" }); return { finding: f.id }; },
        done: (ctx, d) => !!d.finding,
        text: "No camera or detection model is connected, so the operator records what an inspector would report. The finding is labelled illustrative everywhere." },
      { title: "Open an incident follow-up", label: "Open incident follow-up",
        act: async (ctx, d) => { const c = await api(`/api/findings/${d.finding}/case`, { opened_by: "operator" }); location.hash = `#/cases/${c.id}`; return { case: c.id }; },
        done: (ctx, d) => !!d.case,
        text: "The finding becomes an incident follow-up, so nothing is forgotten." },
      { title: "Record the intervention", label: "Record intervention (technician)",
        act: async (ctx, d) => { ctx.setRole("technician"); await api(`/api/cases/${d.case}/action`, { technician: ctx.names.technician, action: "Pallets removed from the east exit; floor marking repainted." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.action,
        text: "The technician says what was done. (The demo switches the role to Technician.)" },
      { title: "A second person checks the work", label: "Verify the work (second person)",
        act: async (ctx, d) => { ctx.setRole("verifier"); await api(`/api/cases/${d.case}/verify`, { verifier: ctx.names.verifier, approve: true, note: "Exit checked on site." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.verification?.approved,
        text: "Another authorized person must check the work. Nobody can approve their own work." },
      { title: "Follow-up inspection and closure", label: "Send follow-up drone, then confirm",
        act: async (ctx, d) => {
          if (!d.followup) { if (ctx.drone?.active) throw new Error("Wait until the patrol returns to its dock, then try again.");
            const m = await api(`/api/cases/${d.case}/inspection`, {}); return { followup: m.id }; }
          const m = ctx.drone?.missions.find(x => x.id === d.followup);
          if (m?.status !== "COMPLETED") throw new Error("The follow-up drone is still flying. Try again when it has landed.");
          await api(`/api/drone/missions/${d.followup}/clear`, { checkpoint: "CP-EE" });
          await api(`/api/cases/${d.case}/close-check`, {}); return {}; },
        done: (ctx, d) => ctx.cases.find(c => c.id === d.case)?.status === "CLOSED",
        text: "Press once to send the drone back, and again after it lands. The incident closes on a simulated inspection, clearly labelled." },
    ],
  },
  sensor: {
    title: "Tour 2 · Early fire warning on real data",
    tag: "REAL RECORDED DATA · HELD-OUT AI MODEL",
    steps: [
      { title: "A normal facility", go: "#/",
        text: "The Overview shows the hall's status, what needs attention and the next action. Monitoring has not started yet." },
      { title: "Choose the authentic Cable#4 recording", go: "#/monitor", label: "Load Cable#4",
        act: async () => { await api("/api/replay/load", { event_id: "Cable#4" }); await api("/api/replay/speed", { speed: 60 }); return {}; },
        done: (ctx) => ctx.state?.event_id === "Cable#4",
        text: "A real cable fire recorded in an industrial hall (Otto von Guericke University dataset). It is analysed by a model that was trained without this event." },
      { title: "Start the replay", go: "#/monitor", label: "Play at 60×",
        act: async () => { await api("/api/replay/play", {}); return {}; },
        done: (ctx) => !!sensorCase(ctx),
        text: "Each 10-second tick, the model scores only readings already played. Watch the fire likelihood rise with CO and particles. The replay pauses itself when a Safety Case opens." },
      { title: "Risk classification", go: "#/monitor",
        text: "Two sensors agree for 30 seconds: Critical alert. In tests on 32 recorded events, the AI warned earlier than a simple smoke-type rule on 14 of 16 fires (about 3 minutes, median 195 s), with similar false alarms." },
      { title: "An incident follow-up opened automatically",
        act: async (ctx) => { const c = sensorCase(ctx); location.hash = `#/cases/${c.id}`; return { case: c.id }; }, label: "Open the incident",
        done: (ctx, d) => !!d.case,
        text: "ARGOS saved the sensor readings and asked for a drone inspection. The drone waits for your approval." },
      { title: "Firefighter Emergency Pack", label: "Show the QR code",
        act: async (ctx, d) => { location.hash = `#/cases/${d.case}`; const v = await api(`/api/cases/${d.case}/pack`);
          setTimeout(() => document.getElementById("firepack")?.scrollIntoView({ behavior: "smooth", block: "center" }), 300);
          return { packUrl: v.local_url, packState: v.state }; },
        done: (ctx, d) => d.packState === "ACTIVE",
        text: "The incident is CRITICAL, so ARGOS issued a Firefighter Emergency Pack automatically. The QR code holds only a short-lived link for this incident, not the data. Demo access, fictional factory layout." },
      { title: "What the firefighter sees", label: "Open the emergency briefing",
        act: async (ctx, d) => { const a = document.createElement("a"); a.href = d.packUrl; a.target = "_blank"; a.rel = "noopener";
          document.body.appendChild(a); a.click(); a.remove(); return { packOpened: true }; },
        text: "Scanning the QR code opens this mobile page: severity, where, nearby hazards, the demonstration factory map, sensor and AI analysis, access points and the timeline. Facts, sensor observations, AI hypotheses and unknowns are kept apart." },
      { title: "Offline backup", label: "Download the briefing PDF",
        act: async (ctx, d) => { const a = document.createElement("a"); a.href = `/api/cases/${d.case}/pack/briefing.pdf`; a.download = `ARGOS_firefighter_briefing_${d.case}.pdf`; document.body.appendChild(a); a.click(); a.remove(); return { packPdf: true }; },
        done: (ctx, d) => !!d.packPdf,
        text: "The QR page needs network access to the ARGOS server. The printable PDF (summary, map, access and hazards, timeline) is the offline backup." },
      { title: "Approve the targeted inspection", label: "Approve drone flight",
        act: async (ctx, d) => { const m = ctx.drone?.missions.find(x => x.case_id === d.case && x.status === "AWAITING_APPROVAL");
          if (!m) throw new Error("No inspection waiting for approval for this case."); await api(`/api/drone/missions/${m.id}/actions/approve`, {}); return { mission: m.id }; },
        done: (ctx, d) => !!d.mission,
        text: "The operator stays in control: the drone only flies after approval. Simulated mission." },
      { title: "Record the intervention", label: "Record intervention (technician)",
        act: async (ctx, d) => { ctx.setRole("technician"); await api(`/api/cases/${d.case}/action`, { technician: ctx.names.technician, action: "Isolated the cable-tray circuit near N6/N7 and removed burnt insulation." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.action, text: "The technician records the intervention." },
      { title: "A second person checks the work", label: "Verify the work (second person)",
        act: async (ctx, d) => { ctx.setRole("verifier"); await api(`/api/cases/${d.case}/verify`, { verifier: ctx.names.verifier, approve: true, note: "Checked on site." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.verification?.approved, text: "A different person approves." },
      { title: "Collect post-action readings", label: "Resume replay", go: "#/monitor",
        act: async () => { await api("/api/replay/speed", { speed: 120 }); await api("/api/replay/play", {}); return {}; },
        done: (ctx) => !!ctx.state?.finished,
        text: "The replay continues with the real recording after the fire, until just before the next experiment in the dataset." },
      { title: "Check recovery", label: "Check recovery",
        act: async (ctx, d) => { location.hash = `#/cases/${d.case}`; await api(`/api/cases/${d.case}/close-check`, {}); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.stabilization,
        text: "ARGOS closes an incident only after 15 minutes of live normal readings. Here the sensors repeated old values after the fire, so ARGOS keeps the incident open and explains why." },
      { title: "Equipment history", go: "#/passport", text: "The hall's history now includes the incident, the inspection and every decision." },
      { title: "Event timeline", go: "#/blackbox", text: "Everything that happened, in order, and who or what did it." },
    ],
  },
};

function Guide({ ctx, demo, setDemo }) {
  if (!demo) return null;
  const sc = SCENARIOS[demo.scenario], st = sc.steps[demo.i];
  const ok = st.done ? st.done(ctx, demo.data) : true;
  const run = async () => { try { const patch = await st.act(ctx, demo.data); setDemo({ ...demo, data: { ...demo.data, ...(patch || {}) } }); await ctx.refreshAll(); } catch (e) { ctx.toast(e.message, true); } };
  const goto = (i) => { setDemo({ ...demo, i }); const g = sc.steps[i].go; if (g) location.hash = g; };
  return html`<div class="guide">
    <div class="row between"><b>${sc.title}</b><button class="btn sm ghost" title="Exit the guided tour" onClick=${() => setDemo(null)}>Exit ✕</button></div>
    <div class="tagline">${sc.tag}</div>
    <div class="gstep">Step ${demo.i + 1} of ${sc.steps.length}</div><div class="gbar"><i style=${`width:${(demo.i + 1) / sc.steps.length * 100}%`}></i></div>
    <h3>${st.title}</h3><p>${st.text}</p>
    <div class="row">
      ${st.act && html`<button class="btn primary" onClick=${run}>${st.label || "Do it"}</button>`}
      ${st.go && html`<a class="btn ghost" href=${st.go}>Show screen</a>`}
      <span class="grow"></span>
      ${demo.i > 0 && html`<button class="btn sm ghost" onClick=${() => goto(demo.i - 1)}>← Back</button>`}
      ${demo.i < sc.steps.length - 1 ? html`<button class="btn sm" disabled=${!ok} title=${ok ? "" : "Complete this step first"} onClick=${() => goto(demo.i + 1)}>Next →</button>`
        : html`<button class="btn sm" onClick=${() => setDemo(null)}>Finish</button>`}
    </div>
    ${!ok && st.done && html`<div class="muted" style="font-size:12px;margin-top:6px">${st.act ? "Press the button above, then wait for the result." : "Waiting for this to happen…"}</div>`}
  </div>`;
}

function DemoPicker({ onPick, onClose }) {
  return html`<div class="modal" onClick=${onClose}><div class="card dialog" onClick=${e => e.stopPropagation()}>
    <div class="welcome"><img src="assets/argos-mark-white.png" alt="ARGOS logo"/><div><h2 style="margin:0">Guided tour</h2><div class="muted">ARGOS · One Step Ahead</div></div></div>
    <p class="muted">Two scenarios. Every step uses the real application; you can also click around freely at any time.</p>
    <div class="grid g2">
      <button class="ev" onClick=${() => onPick("patrol")}><b>1 · Routine drone inspection</b><small>Scheduled patrol, route, checkpoints, an illustrative finding, Safety Case, corrective action, verification, follow-up inspection.</small><span class="pill sim">simulated drone</span></button>
      <button class="ev" onClick=${() => onPick("sensor")}><b>2 · Early fire warning on real data</b><small>Authentic Cable#4 recording, held-out AI model, CRITICAL risk, automatic Safety Case, targeted inspection, verification, stabilization refusal, Passport, Black Box.</small><span class="pill rec">real recorded data</span></button>
    </div>
    <div class="row" style="margin-top:12px"><button class="btn sm ghost" onClick=${async () => { if (confirm("Clear all demo cases, missions and events before starting?")) { await api("/api/demo/reset", {}); location.reload(); } }}>Start from a clean slate</button><span class="grow"></span><button class="btn ghost" onClick=${onClose}>Close</button></div>
  </div></div>`;
}

// ------------------------------------------------------------------ app shell
const NAV = [
  ["OPERATIONS"], ["#/", "◎", "Overview"], ["#/monitor", "◉", "Live Monitoring"], ["#/drone", "✈", "Drone Inspections"], ["#/cases", "◆", "Incident Follow-up"],
  ["RECORDS"], ["#/passport", "▤", "Equipment History"], ["#/blackbox", "◷", "Event Timeline"], ["#/firepack", "✚", "Emergency Fire Pack"],
  ["ADVANCED"], ["#/evidence", "∑", "AI Evidence"],
];

function App() {
  const hash = useHash();
  const [facility, setFacility] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [state, setState] = useState(null);
  const [ticks, setTicks] = useState([]);
  const [cases, setCases] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [drone, setDrone] = useState(null);
  const [role, setRole] = useState("operator");
  const [names] = useState({ technician: "Amine B. (technician)", verifier: "Sami K. (HSE verifier)" });
  const [msg, setMsg] = useState(null);
  const [online, setOnline] = useState(true);
  // the tour survives a reload or a same-tab navigation (e.g. opening the firefighter briefing)
  const [demo, setDemoRaw] = useState(() => { try { return JSON.parse(sessionStorage.getItem("argos-tour")) || null; } catch (e) { return null; } });
  const setDemo = (d) => { setDemoRaw(d); try { d ? sessionStorage.setItem("argos-tour", JSON.stringify(d)) : sessionStorage.removeItem("argos-tour"); } catch (e) { /* storage unavailable */ } };
  const [picker, setPicker] = useState(false);
  const tickRef = useRef({ event: null, ticks: [] });

  const toast = (text, err) => { setMsg({ text, err }); setTimeout(() => setMsg(null), 5000); };
  useEffect(() => { api("/api/facility").then(setFacility).catch(() => setOnline(false)); api("/api/replay/catalog").then(setCatalog).catch(() => {}); }, []);

  const refresh = useCallback(async () => {
    try {
      const s = await api("/api/replay/state");
      setOnline(true);
      const tr = tickRef.current;
      if (s.event_id !== tr.event || (s.progress === 0 && tr.ticks.length)) tickRef.current = { event: s.event_id, ticks: [] };
      const since = tickRef.current.ticks.length;
      if (s.event_id) {
        const ser = await api(`/api/replay/series?since=${since}`);
        if (ser.ticks.length) { tickRef.current.ticks = tickRef.current.ticks.concat(ser.ticks); setTicks(tickRef.current.ticks.slice()); }
        else if (!since) setTicks([]);
      } else setTicks([]);
      setState(s);
    } catch (e) { setOnline(false); }
  }, []);
  const refreshCases = useCallback(async () => { setCases(await api("/api/cases")); setAlerts(await api("/api/alerts")); }, []);
  const refreshDrone = useCallback(async () => { setDrone(await api("/api/drone")); }, []);
  const refreshAll = useCallback(async () => { await Promise.all([refresh(), refreshCases().catch(() => {}), refreshDrone().catch(() => {})]); }, []);
  usePoll(refresh, 800, []);
  usePoll(refreshCases, 1500, []);
  usePoll(refreshDrone, 700, []);

  const ctx = { facility, catalog, state, ticks, cases, alerts, drone, refresh, refreshDrone, refreshAll, toast, role, setRole, names };
  const open = cases.filter(c => c.status !== "CLOSED").length;
  const awaiting = (drone?.missions || []).filter(m => m.status === "AWAITING_APPROVAL").length;
  const route = hash.replace(/^#/, "");
  let page, title, sub;
  if (route.startsWith("/cases/")) { const id = route.split("/")[2]; page = html`<${CaseDetail} id=${id} ctx=${ctx} key=${id}/>`; title = `Incident ${id}`; sub = "What happened, what to do, and who does it"; }
  else ({
    "/": () => { page = html`<${Overview} ctx=${ctx}/>`; title = "Overview"; sub = "ARGOS · One Step Ahead"; },
    "/monitor": () => { page = html`<${Monitor} ctx=${ctx}/>`; title = "Live Monitoring"; sub = "Sensor readings and AI fire warning"; },
    "/drone": () => { page = html`<${DroneOps} ctx=${ctx}/>`; title = "Drone Inspections"; sub = "Routine patrols and alert inspections (simulated drone)"; },
    "/cases": () => { page = html`<${Cases} ctx=${ctx}/>`; title = "Incident Follow-up"; sub = "Every problem, from detection to verified completion"; },
    "/passport": () => { page = html`<${Passport} ctx=${ctx}/>`; title = "Equipment History"; sub = "Incidents, inspections and records for the hall"; },
    "/blackbox": () => { page = html`<${BlackBox} ctx=${ctx}/>`; title = "Event Timeline"; sub = "Everything that happened, in order (black box)"; },
    "/firepack": () => { page = html`<${FirePack} ctx=${ctx}/>`; title = "Emergency Fire Pack"; sub = "Emergency information for authorized responders"; },
    "/evidence": () => { page = html`<${Evidence} ctx=${ctx}/>`; title = "AI Evidence"; sub = "What the tests on real data show, and what they do not"; },
  }[route] || (() => { page = html`<div class="page"><div class="empty">Page not found. <a href="#/">Back to the Overview</a></div></div>`; title = "Not found"; }))();

  return html`<div class="shell">
    <aside class="side">
      <div class="brand"><img src="assets/argos-mark-white.png" alt="ARGOS logo"/><div><b>ARGOS</b><span>One Step Ahead</span></div></div>
      <nav class="nav">${NAV.map(([h, i, t]) => !i ? html`<div class="nav-group">${h}</div>` : html`<a href=${h} class=${(h === "#/" ? hash === "#/" || hash === "" : hash.startsWith(h)) ? "on" : ""} aria-current=${(h === "#/" ? hash === "#/" || hash === "" : hash.startsWith(h)) ? "page" : null}>
        <span class="ico">${i}</span>${t}${t === "Incident Follow-up" && open ? html`<span class="badge" title="open incidents">${open}</span>` : ""}${t === "Drone Inspections" && awaiting ? html`<span class="badge warn" title="waiting for approval">${awaiting}</span>` : ""}</a>`)}</nav>
      <div class="foot">Prototype · sensor data replayed from real recordings (Industrial Hall dataset, CC BY 4.0) · drone simulated · demo roles
        <div style="margin-top:8px"><button class="btn sm ghost" onClick=${async () => { if (confirm("Clear all demo cases, missions and events?")) { await api("/api/demo/reset", {}); setDemo(null); location.hash = "#/"; refreshAll(); } }}>Reset demo</button></div></div>
    </aside>
    <main class="main">
      <div class="top"><div><h1>${title}</h1><div class="sub">${sub}</div></div><span class="grow"></span>
        ${!online && html`<span class="pill bad">backend offline: start the server</span>`}
        <button class="btn primary" onClick=${() => setPicker(true)}>▶ Guided tour</button>
        <label class="role"><small>Demo role</small><select value=${role} onChange=${e => setRole(e.target.value)}>
          <option value="operator">Control-room operator</option><option value="technician">${names.technician}</option><option value="verifier">${names.verifier}</option></select></label>
      </div>
      ${page}
    </main>
    <${Guide} ctx=${ctx} demo=${demo} setDemo=${setDemo}/>
    ${picker && html`<${DemoPicker} onClose=${() => setPicker(false)} onPick=${(s) => { setPicker(false); setDemo({ scenario: s, i: 0, data: {} }); const g = SCENARIOS[s].steps[0].go; if (g) location.hash = g; }}/>`}
    ${msg && html`<div class=${`toast ${msg.err ? "err" : ""}`}>${msg.text}</div>`}
  </div>`;
}

render(html`<${App}/>`, document.getElementById("app"));
