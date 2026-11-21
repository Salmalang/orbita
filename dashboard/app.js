/* AEROGUARD TRUST — control-room UI (Preact + htm, no build step). */
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
const LEVEL_TEXT = { NORMAL: "NORMAL", WATCH: "WATCH", HIGH: "HIGH", CRITICAL: "CRITICAL", NO_DATA: "NO DATA", STANDBY: "STANDBY" };
const LEVEL_COLOR = { NORMAL: "#22c55e", WATCH: "#3b82f6", HIGH: "#f59e0b", CRITICAL: "#ef4444", NO_DATA: "#64748b" };
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
const nodeColor = (n, fireNodes) => !n ? "#334155" : fireNodes?.includes(n.id) ? LEVEL_COLOR.CRITICAL
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
        plugins: { legend: { labels: { color: "#a9b4c8", boxWidth: 10, font: { size: 11 } } },
                   tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y == null ? "—" : c.parsed.y.toFixed(3)}${unit ? " " + unit : ""}` } } },
        scales: {
          x: { ticks: { color: "#6b7891", maxTicksLimit: 7, autoSkip: true, font: { size: 10 } }, grid: { color: "rgba(255,255,255,.04)" } },
          y: { ticks: { color: "#6b7891", font: { size: 10 } }, grid: { color: "rgba(255,255,255,.06)" }, min: yMin, max: yMax },
        },
        elements: { point: { radius: 0 }, line: { borderWidth: 1.8, tension: 0.15 } },
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
  const W = facility.dimensions_m.length, H = facility.dimensions_m.width, s = 40, pad = 30;
  return html`<div class="map">
    <svg viewBox=${`0 0 ${W * s + pad * 2} ${H * s + pad * 2}`} role="img" aria-label="Hall map with sensor nodes">
      <rect x=${pad} y=${pad} width=${W * s} height=${H * s} rx="10" fill="#0d1422" stroke="#2c3d5e" stroke-width="2"/>
      ${[...Array(W)].map((_, i) => html`<line x1=${pad + i * s} y1=${pad} x2=${pad + i * s} y2=${pad + H * s} stroke="rgba(255,255,255,.03)"/>`)}
      <text x=${pad + 10} y=${pad + 20} fill="#5d6a84" font-size="13">${facility.name} · ${W} × ${H} m (layout illustrative)</text>
      ${showExits && facility.exits.map(e => html`<g>
        <rect x=${pad + e.x * s - 7} y=${pad + e.y * s - 22} width="14" height="44" fill="#16a34a"/>
        <text x=${pad + e.x * s + (e.x === 0 ? -2 : 2)} y=${pad + e.y * s - 30} text-anchor=${e.x === 0 ? "start" : "end"} fill="#4ade80" font-size="12">EXIT · ${e.label}</text></g>`)}
      ${facility.drone_dock && html`<g><rect x=${pad + facility.drone_dock.x * s - 12} y=${pad + facility.drone_dock.y * s - 12} width="24" height="24" rx="5" fill="none" stroke="#a78bfa" stroke-dasharray="3 3"/>
        <text x=${pad + facility.drone_dock.x * s + 18} y=${pad + facility.drone_dock.y * s + 4} fill="#a78bfa" font-size="11">drone dock (simulated)</text></g>`}
      ${facility.nodes.map(n => {
        const st = nodes?.[n.id]; const col = nodeColor(st && { ...st, id: n.id }, fireNodes);
        const cx = pad + n.x * s, cy = pad + n.y * s;
        return html`<g style="cursor:pointer" onClick=${() => onPick && onPick(n.id)}>
          ${fireNodes?.includes(n.id) && html`<circle cx=${cx} cy=${cy} r="30" fill=${col} opacity=".18"><animate attributeName="r" values="20;34;20" dur="1.6s" repeatCount="indefinite"/></circle>`}
          <circle cx=${cx} cy=${cy} r="15" fill=${col} stroke=${picked === n.id ? "#fff" : "#0a0f1a"} stroke-width="3"/>
          <text x=${cx} y=${cy + 4} text-anchor="middle" fill="#0a0f1a" font-size="10" font-weight="700">${n.label}</text>
          ${st && html`<text x=${cx} y=${cy + 32} text-anchor="middle" fill="#8d9ab3" font-size="10.5">fire ${pct(st.p_fire)}</text>`}
        </g>`;
      })}
      ${drone && facility.checkpoints && facility.checkpoints.map(c => html`<g>
        <rect x=${pad + c.x * s - 7} y=${pad + c.y * s - 7} width="14" height="14" transform=${`rotate(45 ${pad + c.x * s} ${pad + c.y * s})`}
          fill=${mission?.checkpoints.find(x => x.id === c.id)?.result === "finding" ? "#f59e0b" : mission?.checkpoints.find(x => x.id === c.id)?.status === "inspected" ? "#a78bfa" : "#1e293b"} stroke="#a78bfa" stroke-width="1.5"/>
        <text x=${pad + c.x * s} y=${pad + c.y * s - 13} text-anchor="middle" fill="#c4b5fd" font-size="10">${c.label.split(" (")[0].split(",")[0]}</text></g>`)}
      ${mission && html`<polyline points=${mission.path.map(p => `${pad + p.x * s},${pad + p.y * s}`).join(" ")} fill="none" stroke="#a78bfa" stroke-width="2" stroke-dasharray="6 5" opacity=".75"/>`}
      ${drone?.active && html`<g transform=${`translate(${pad + drone.active.position.x * s} ${pad + drone.active.position.y * s})`}>
        <circle r="16" fill="rgba(167,139,250,.18)"><animate attributeName="r" values="12;20;12" dur="1.2s" repeatCount="indefinite"/></circle>
        <path d="M-9 0 H9 M0 -9 V9" stroke="#ede9fe" stroke-width="2.5"/><circle r="4.5" fill="#a78bfa" stroke="#ede9fe" stroke-width="1.5"/>
        <text y="26" text-anchor="middle" fill="#ddd6fe" font-size="10.5" font-weight="700">DRONE (simulated)</text></g>`}
    </svg>
    <div class="legend"><span><i style="background:#22c55e"></i>normal</span><span><i style="background:#3b82f6"></i>nuisance-like</span>
      <span><i style="background:#f59e0b"></i>fire signal</span><span><i style="background:#ef4444"></i>confirmed fire node</span><span><i style="background:#334155"></i>no data yet</span>${drone ? html`<span><i style="background:#a78bfa;border-radius:2px"></i>drone checkpoint</span>` : ""}</div>
  </div>`;
}

function RiskBanner({ decision, compact }) {
  const lvl = decision?.level || "NO_DATA";
  const reasons = decision?.reasons || ["Load a recorded event and start the replay"];
  return html`<div class=${`risk ${lvl}`}>
    <div class="lvl">${LEVEL_TEXT[lvl]}</div>
    <div class="why">${reasons[0]}</div>
    <div class="more">${compact ? "" : reasons.slice(1, 3).join(" · ")}${decision ? ` · operational priority ${decision.score}/100 (not a probability)` : ""}</div>
  </div>`;
}

// ------------------------------------------------------------------ pages
const GLOSS = {
  pfire: "Model confidence (0–100 %) that a sensor node's readings look like a fire, computed from the real recorded readings. Not a calibrated probability.",
  replay: "Historical replay: real sensor readings recorded in an industrial hall during controlled experiments (July 2023), played back as if live.",
  sim: "Simulated: no physical drone is connected. Movement, schedules and findings demonstrate the workflow only.",
};
const Info = ({ k }) => html`<span class="info" title=${GLOSS[k]}>ⓘ</span>`;
const MODE_LABEL = { PREVENTIVE: "Preventive patrol", TARGETED: "Alert-triggered inspection", FOLLOW_UP: "Follow-up inspection" };
const ORIGIN_LABEL = { SCHEDULED: "scheduled", MANUAL: "started manually", ALERT: "requested by a sensor alert", FOLLOW_UP: "verification after corrective action" };
const inMin = (iso) => { if (!iso) return "—"; const m = Math.round((new Date(iso) - Date.now()) / 60000); return m <= 0 ? "due now" : m < 60 ? `in ${m} min` : `in ${Math.floor(m / 60)} h ${m % 60} min`; };

function Overview({ ctx }) {
  const { facility, state, cases, drone } = ctx;
  const dec = state?.latest?.decision;
  const level = dec?.level || (state?.event_id ? "NO_DATA" : "NORMAL");
  const open = cases.filter(c => c.status !== "CLOSED");
  const critical = open.filter(c => c.severity === "CRITICAL");
  const awaiting = (drone?.missions || []).filter(m => m.status === "AWAITING_APPROVAL");
  const loose = (drone?.findings || []).filter(f => !f.case_id);
  const active = drone?.active;
  const sched = (drone?.schedules || []).filter(s => s.enabled).sort((a, b) => a.next_due.localeCompare(b.next_due))[0];
  const route = (id) => drone?.routes?.find(r => r.id === id)?.label || id;

  const headline = level === "CRITICAL" || critical.length ? ["CRITICAL", "Fire signature confirmed — respond now"]
    : level === "HIGH" ? ["HIGH", "Possible fire signal on one sensor — checking"]
    : open.length || awaiting.length || loose.length ? ["WATCH", "No fire signal — open items need your attention"]
    : !state?.event_id ? ["STANDBY", "No active alert — sensor replay not started"]
    : level === "NO_DATA" ? ["NO_DATA", "Sensors not delivering live data — status unknown"]
    : ["NORMAL", "No fire signal — facility normal"];

  const todo = [];
  awaiting.forEach(m => todo.push({ t: `Approve the alert-triggered drone inspection for ${m.case_id}`, href: "#/drone", b: "Review mission" }));
  critical.forEach(c => todo.push({ t: `Respond to ${c.id}: ${c.findings[0]}`, href: `#/cases/${c.id}`, b: "Open case" }));
  open.filter(c => c.severity !== "CRITICAL").forEach(c => todo.push({ t: `${c.id} is ${c.status.replaceAll("_", " ").toLowerCase()}: next step ${c.status === "OPEN" ? "corrective action" : c.status === "ACTION_RECORDED" ? "independent verification" : "closure check"}`, href: `#/cases/${c.id}`, b: "Open case" }));
  loose.forEach(f => todo.push({ t: `Decide on inspection finding ${f.id}: ${f.type_label} at ${f.checkpoint_label}`, href: "#/drone", b: "Review finding" }));
  if (!todo.length) todo.push({ t: "Nothing pending. Start the guided demo, replay a recorded event or launch a preventive patrol.", href: "#/monitor", b: "Live monitoring" });

  return html`<div class="page">
    <div class=${`hero ${headline[0]}`}>
      <div><div class="q">Is my facility safe?</div><div class="a">${headline[1]}</div>
        <div class="sub2">${facility?.name} · ${facility?.site} · ${state?.event_id ? html`sensor status from a historical replay of real data <${Info} k="replay"/>` : "no sensor feed: open Live Monitoring to replay a recorded event"}</div></div>
      <div class="lvl">${LEVEL_TEXT[headline[0]]}</div>
    </div>

    <div class="grid g-main">
      <div class="card"><h2>What should I do next? <span class="r">${todo.length} item${todo.length > 1 ? "s" : ""}</span></h2>
        <div class="stack">${todo.slice(0, 6).map((x, i) => html`<div class="todo"><span class="n">${i + 1}</span><span>${x.t}</span><a class="btn sm" href=${x.href}>${x.b} →</a></div>`)}</div>
      </div>
      <div class="stack">
        <div class="card"><h2>Drone <span class="r"><span class="pill sim">SIMULATED</span></span></h2>
          ${active ? html`<div><b>${MODE_LABEL[active.mode]}</b> · ${active.label}</div>
              <div class="bar"><i style=${`width:${Math.round(active.progress * 100)}%`}></i></div>
              <div class="muted">${active.status === "PAUSED" ? "Paused" : active.current || "Taking off"} · ${Math.round(active.progress * 100)} %</div>`
            : html`<div class="muted">On dock. No mission in flight.</div>`}
          <div style="margin-top:8px">Next preventive patrol: <b>${sched ? `${route(sched.route_id)} ${inMin(sched.next_due)}` : "none scheduled"}</b></div>
          <a class="btn sm" style="margin-top:8px" href="#/drone">Drone Operations →</a></div>
        <div class="card"><h2>Pending Safety Cases</h2>
          ${open.length ? open.slice(0, 4).map(c => html`<div class="row between" style="padding:4px 0"><a href=${`#/cases/${c.id}`}><b>${c.id}</b></a>
              <span class="muted">${c.kind === "INSPECTION_FINDING" ? "inspection finding" : "sensor alert"}</span><span class=${`pill ${c.status}`}>${c.status.replaceAll("_", " ")}</span></div>`)
            : html`<div class="empty">No open case</div>`}</div>
      </div>
    </div>

    <div class="grid g-main">
      <div class="card"><h2>Monitored zone · ${facility?.name} <span class="r">${facility?.nodes.length} sensor nodes</span></h2>
        <${HallMap} facility=${facility} nodes=${state?.latest?.nodes || {}} fireNodes=${dec?.fire_nodes} drone=${drone}/>
        <div class="muted" style="font-size:12.5px;margin-top:6px">${facility?.illustrative_note}</div></div>
      <div class="card"><h2>Recent inspection findings <span class="r"><span class="pill sim">ILLUSTRATIVE</span></span></h2>
        ${(drone?.findings || []).length ? drone.findings.slice(0, 5).map(f => html`<div style="padding:6px 0;border-bottom:1px solid var(--line)">
            <div class="row between"><b>${f.type_label}</b><span class=${`pill ${f.severity === "HIGH" ? "CRITICAL" : f.severity === "MEDIUM" ? "HIGH" : "WATCH"}`}>${f.severity}</span></div>
            <div class="muted">${f.checkpoint_label} · ${f.case_id ? html`<a href=${`#/cases/${f.case_id}`}>${f.case_id}</a>` : "no case yet"}</div></div>`)
          : html`<div class="empty">No finding recorded yet. Findings come from drone inspections.</div>`}</div>
    </div>
  </div>`;
}

function Monitor({ ctx }) {
  const { facility, state, ticks, catalog, refresh, toast } = ctx;
  const [picked, setPicked] = useState(null);
  const [nodeHist, setNodeHist] = useState(null);
  const dec = state?.latest?.decision;
  const nodes = state?.latest?.nodes || {};
  const ev = catalog.find(e => e.id === state?.event_id);
  const act = async (p, b) => { try { await api(p, b ?? {}); await refresh(); } catch (e) { toast(e.message, true); } };
  const load = async (id) => { await act("/api/replay/load", { event_id: id }); setPicked(null); setNodeHist(null); };

  useEffect(() => { if (!picked) return; let alive = true;
    const run = () => api(`/api/replay/node/${picked}`).then(d => alive && setNodeHist(d)).catch(() => {});
    run(); const id = setInterval(run, 2500); return () => { alive = false; clearInterval(id); }; }, [picked, state?.event_id]);

  const labels = useMemo(() => ticks.map(t => fmtT(t.t)), [ticks]);
  const S = (key, f = (x) => x) => ticks.map(t => (t[key] == null ? null : f(t[key])));
  const M = (ch) => ticks.map(t => t.mean?.[ch] ?? null);
  const span = state?.window_start ? (new Date(state.window_end) - new Date(state.window_start)) : 1;
  const at = (iso) => iso && state?.window_start ? Math.max(0, Math.min(100, (new Date(iso) - new Date(state.window_start)) / span * 100)) : 0;
  const nodeLabel = (id) => facility?.nodes.find(n => n.id === id)?.label || id;

  return html`<div class="page">
    <div class="banner info">ⓘ <div><b>What you are watching:</b> real sensor readings recorded in an industrial hall during controlled fire and nuisance experiments, replayed as if live <${Info} k="replay"/>. Every 10 s the AI scores only the readings already played. Rule: when <b>two sensors</b> agree on a fire signature for 30 s, the zone becomes <b>CRITICAL</b> and a Safety Case opens.</div></div>
    <div class="card"><h2>1 · Choose an authentic recorded event <span class="r muted">Industrial Hall dataset · held-out models</span></h2>
      <div class="events">${catalog.map(e => html`<button class=${`ev ${state?.event_id === e.id ? "on" : ""}`} onClick=${() => load(e.id)}>
        <div class="row between"><b>${e.id}</b><span class=${`pill ${e.truth === "fire" ? "CRITICAL" : "WATCH"}`}>${e.truth === "fire" ? "real fire" : "nuisance"}</span></div>
        <small>${e.description}</small><small class="dim">${e.duration_min} min · ${fmtT(e.start, true)}</small></button>`)}</div>
      <div class="muted" style="margin-top:10px;font-size:12.5px">Each event is analysed by a model trained <b>without</b> that event. Welding is shown as a known limitation: the training data contains a single welding recording, so the model has never seen welding when replaying it.</div>
    </div>

    ${state?.event_id && html`<div class="card"><h2>2 · Replay controls <span class="r"><span class="pill rec">● HISTORICAL REPLAY · recorded ${fmtT(state.cursor, true)}</span></span></h2>
      <div class="row">
        ${state.running ? html`<button class="btn" onClick=${() => act("/api/replay/pause")}>❚❚ Pause</button>`
          : html`<button class="btn primary" disabled=${state.finished} onClick=${() => act("/api/replay/play")}>▶ ${state.progress > 0 ? "Resume" : "Start replay"}</button>`}
        <button class="btn" disabled=${state.running || state.finished} onClick=${() => act("/api/replay/step", { ticks: 6 })}>Step +1 min</button>
        <span class="muted">Speed</span>
        <div class="seg">${(state.speeds || []).map(s => html`<button class=${state.speed === s ? "on" : ""} onClick=${() => act("/api/replay/speed", { speed: s })}>${s}×</button>`)}</div>
        <span class="grow"></span>
        <span class="muted mono">model ${state.model}</span>
      </div>
      <div class="progress" style="margin-top:12px">
        <div class="evband" style=${`left:${at(state.event_start)}%;width:${at(state.event_end) - at(state.event_start)}%`}></div>
        <div class="fill" style=${`width:${state.progress * 100}%`}></div>
        <div class="lab"><span>${fmtT(state.window_start)}</span><span>▨ labelled event ${fmtT(state.event_start)}–${fmtT(state.event_end)}</span><span>${fmtT(state.window_end)}</span></div>
      </div>
      ${state.finished && html`<div class="muted" style="margin-top:8px">End of the recording window (stops before the next experiment in the dataset).</div>`}
    </div>`}

    ${state?.event_id && html`<${RiskBanner} decision=${dec}/>`}

    ${state?.event_id && html`<div class="grid g-main">
      <div class="card"><h2>3 · AI analysis over time <span class="r muted">computed tick by tick, never on future data</span></h2>
        <${LineChart} labels=${labels} height=${230} yMin=${0} yMax=${1}
          series=${[{ label: "fire likelihood, highest sensor (0–1)", data: S("max_p_fire"), color: "#ef4444", fill: "rgba(239,68,68,.08)" },
                    { label: "nuisance likelihood, highest sensor (0–1)", data: S("max_p_nuisance"), color: "#3b82f6" }]}
          thresholds=${[{ label: "fire threshold 0.95", value: 0.95, color: "rgba(255,255,255,.35)" }]}/>
        <div class="grid g2" style="margin-top:10px">
          <div><div class="muted" style="font-size:12px;margin-bottom:4px">Carbon monoxide (mean of reporting nodes)</div>
            <${LineChart} labels=${labels} height=${160} unit="ppm" series=${[{ label: "CO (ppm)", data: M("co_ppm"), color: "#f59e0b" }]}/></div>
          <div><div class="muted" style="font-size:12px;margin-bottom:4px">Particles (mean count)</div>
            <${LineChart} labels=${labels} height=${160} series=${[{ label: "particles (count)", data: M("pm_total"), color: "#a78bfa" }]}/></div>
          <div><div class="muted" style="font-size:12px;margin-bottom:4px">VOC (raw sensor value)</div>
            <${LineChart} labels=${labels} height=${160} series=${[{ label: "VOC (raw)", data: M("voc_raw"), color: "#14b8a6" }]}/></div>
          <div><div class="muted" style="font-size:12px;margin-bottom:4px">Air temperature (°C)</div>
            <${LineChart} labels=${labels} height=${160} unit="°C" series=${[{ label: "temperature (°C)", data: M("temperature_c"), color: "#f472b6" }]}/></div>
        </div>
      </div>
      <div class="stack">
        <div class="card"><h2>Hall · 9 sensor nodes <span class="r muted">click a node</span></h2>
          <${HallMap} facility=${facility} nodes=${nodes} fireNodes=${dec?.fire_nodes} onPick=${setPicked} picked=${picked} showExits=${false}/></div>
        <div class="card"><h2>Node readings at ${fmtT(state.cursor)}</h2>
          <table class="t"><thead><tr><th>Node</th><th class="num" title=${GLOSS.pfire}>Fire ⓘ</th><th class="num">Nuisance</th><th class="num">CO ppm</th><th class="num">particles</th></tr></thead>
          <tbody>${facility?.nodes.map(n => { const s = nodes[n.id]; const stale = dec?.unhealthy_nodes?.includes(n.id);
            return html`<tr class="click" onClick=${() => setPicked(n.id)} style=${picked === n.id ? "background:var(--panel2)" : ""}>
              <td><b>${n.label}</b>${stale && html` <span class="pill NO_DATA">no data</span>`}${dec?.fire_nodes?.includes(n.id) && html` <span class="pill CRITICAL">fire</span>`}</td>
              <td class="num">${pct(s?.p_fire)}</td><td class="num">${pct(s?.p_nuisance)}</td>
              <td class="num">${num(s?.readings?.co_ppm, 2)}</td><td class="num">${num(s?.readings?.pm_total, 0)}</td></tr>`; })}</tbody></table>
        </div>
      </div>
    </div>`}

    ${picked && nodeHist && html`<div class="card"><h2>Node ${nodeLabel(picked)} · ${picked} <span class="r"><button class="btn sm ghost" onClick=${() => { setPicked(null); setNodeHist(null); }}>Close ✕</button></span></h2>
      <div class="muted" style="margin-bottom:8px">All readings of this node up to the replay cursor (${nodeHist.points.length} samples, every 10 s). Units: CO ppm, CO₂ ppm, VOC raw, particles count, temperature °C.</div>
      <div class="grid g2">
        <${LineChart} labels=${nodeHist.points.map(p => fmtT(p.t))} yMin=${0} yMax=${1} series=${[
          { label: "P(fire)", data: nodeHist.points.map(p => p.p_fire), color: "#ef4444" }, { label: "P(nuisance)", data: nodeHist.points.map(p => p.p_nuisance), color: "#3b82f6" }]}/>
        <${LineChart} labels=${nodeHist.points.map(p => fmtT(p.t))} series=${[
          { label: "CO (ppm)", data: nodeHist.points.map(p => p.co_ppm), color: "#f59e0b" }, { label: "CO₂ (ppm/100)", data: nodeHist.points.map(p => p.co2_ppm / 100), color: "#94a3b8" },
          { label: "VOC (raw)", data: nodeHist.points.map(p => p.voc_raw), color: "#14b8a6" }]}/>
      </div></div>`}

    ${ctx.cases.find(c => c.status !== "CLOSED") && html`<div class="banner err" style="cursor:pointer" onClick=${() => location.hash = `#/cases/${ctx.cases.find(c => c.status !== "CLOSED").id}`}>
      ⚠ <div><b>Safety Case ${ctx.cases.find(c => c.status !== "CLOSED").id} is open — replay paused automatically.</b> Click to review the evidence and run the response workflow, then come back and resume the replay: the stabilization check needs the real readings recorded after the corrective action.</div></div>`}
  </div>`;
}

const STEPS_SENSOR = [
  ["Sensor alert", "Risk engine · real data"], ["Case opened", "System"], ["Targeted inspection", "Drone · simulated"],
  ["Corrective action", "Technician"], ["Independent check", "Verifier"], ["Stabilization", "System · live readings"],
];
const STEPS_FINDING = [
  ["Finding recorded", "Patrol · illustrative"], ["Case opened", "Operator"], ["Corrective action", "Technician"],
  ["Independent check", "Verifier"], ["Follow-up inspection", "Drone · simulated"], ["Closure check", "System"],
];

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
    : [true, true, targetedDone, !!c.action, !!c.verification?.approved, c.status === "CLOSED"];
  const steps = isFinding ? STEPS_FINDING : STEPS_SENSOR;
  const cur = done.indexOf(false);
  const ev = c.evidence?.nodes || {};
  const fnd = c.evidence?.finding;
  const activeM = missions.find(m => ["AWAITING_APPROVAL", "IN_FLIGHT", "PAUSED"].includes(m.status));
  const canRequest = c.status !== "CLOSED" && !activeM && (!isFinding || c.action);

  return html`<div class="page">
    <div class="row between">
      <div class="row"><a href="#/cases" class="btn sm ghost">← Safety Cases</a><h2 style="margin:0;font-size:20px">${c.id}</h2>
        <span class=${`pill ${c.status}`}>${c.status.replaceAll("_", " ")}</span><span class=${`pill ${c.severity}`}>${c.severity}</span>
        <span class=${`pill ${isFinding ? "sim" : "rec"}`}>${isFinding ? "FROM DRONE PATROL · ILLUSTRATIVE" : "FROM SENSOR AI · REAL DATA REPLAY"}</span>
        ${c.escalations ? html`<span class="pill bad">fire signal returned after action ×${c.escalations}</span>` : ""}</div>
      <span class="muted">${c.zone} · opened ${isFinding ? fmtWall(c.opened_wall_ts) : `at recorded time ${fmtT(c.opened_data_ts, true)} (${c.replay_event})`}</span>
    </div>
    <div class="steps">${steps.map(([t, w], i) => html`<div class=${`step ${done[i] ? "done" : i === cur ? "cur" : ""}`}>
      <div class="n">STEP ${i + 1} · ${w.toUpperCase()}</div><b>${done[i] ? "✓ " : ""}${t}</b></div>`)}</div>

    <div class="grid g-main">
      <div class="stack">
        <div class="card"><h2>${isFinding ? "Inspection finding" : "What the AI found"}</h2>
          <ul style="margin:0 0 10px;padding-left:18px">${c.findings.map(f => html`<li>${f}</li>`)}</ul>
          ${isFinding && fnd && html`<dl class="kv"><dt>Checkpoint</dt><dd>${fnd.checkpoint_label}</dd><dt>Type</dt><dd>${fnd.type_label}</dd>
            <dt>Severity</dt><dd>${fnd.severity}</dd><dt>Mission</dt><dd>${fnd.mission_id} (simulated)</dd><dt>Recorded by</dt><dd>${fnd.recorded_by} · ${fmtWall(fnd.recorded_at)}</dd></dl>
            <div class="banner sim" style="margin-top:10px">${fnd.label}</div>`}
          ${!isFinding && html`<details open><summary class="muted" style="cursor:pointer">Sensor evidence at the moment the case opened <${Info} k="pfire"/></summary>
            <table class="t"><thead><tr><th>Sensor</th><th class="num">Fire likelihood</th><th class="num">Nuisance likelihood</th><th class="num">CO (ppm)</th><th class="num">CO₂ (ppm)</th><th class="num">Particles</th><th class="num">Temp (°C)</th></tr></thead>
            <tbody>${Object.entries(ev).sort((a, b) => b[1].p_fire - a[1].p_fire).map(([k, v]) => html`<tr>
              <td>${ctx.facility?.nodes.find(n => n.id === k)?.label || k} ${c.fire_nodes.includes(k) && html`<span class="pill CRITICAL">fire signal</span>`}</td>
              <td class="num">${pct(v.p_fire)}</td><td class="num">${pct(v.p_nuisance)}</td><td class="num">${num(v.readings.co_ppm, 2)}</td>
              <td class="num">${num(v.readings.co2_ppm, 0)}</td><td class="num">${num(v.readings.pm_total, 0)}</td><td class="num">${num(v.readings.temperature_c, 1)}</td></tr>`)}</tbody></table>
            <div class="muted" style="margin-top:8px;font-size:12px">Recorded readings and held-out model outputs (model ${c.evidence?.model}). Historical replay of real data.</div></details>`}
        </div>
        <div class="card"><h2>Recommended response</h2><div>${c.recommended_inspection}</div>
          <div class="banner info" style="margin-top:10px">Certified fire alarms and emergency shutdown systems act independently of AEROGUARD. This case supports the response; it never replaces them.</div></div>

        <div class="card"><h2>Drone inspections for this case <span class="r"><span class="pill sim">SIMULATED</span></span></h2>
          ${missions.length ? html`<table class="t"><tbody>${missions.map(m => html`<tr><td><b>${m.id}</b> · ${MODE_LABEL[m.mode]}<div class="muted">${m.checkpoints.map(x => `${x.label}${x.result ? ` (${x.result})` : ""}`).join(", ")}</div></td>
            <td><span class=${`pill ${m.status === "COMPLETED" ? "ok" : m.status === "AWAITING_APPROVAL" ? "HIGH" : m.status === "CANCELLED" ? "pending" : "WATCH"}`}>${m.status.replace("_", " ")}</span></td>
            <td class="num">${m.status === "AWAITING_APPROVAL" ? html`<button class="btn sm primary" onClick=${async () => { try { await api(`/api/drone/missions/${m.id}/actions/approve`, {}); await refreshDrone(); } catch (e) { toast(e.message, true); } }}>Approve flight</button>`
              : m.status === "COMPLETED" ? html`${m.checkpoints.filter(x => !x.result).map(x => html`<button class="btn sm" onClick=${async () => { try { await api(`/api/drone/missions/${m.id}/clear`, { checkpoint: x.id }); await refreshDrone(); } catch (e) { toast(e.message, true); } }}>Mark ${x.label.split(" (")[0]} clear</button> `)}` : html`<a class="btn sm" href="#/drone">Watch →</a>`}</td></tr>`)}</tbody></table>`
            : html`<div class="empty">No inspection linked yet.</div>`}
          ${canRequest && html`<button class="btn" style="margin-top:8px" onClick=${() => post("inspection")}>${isFinding || c.action ? "Request follow-up inspection" : "Request targeted inspection"}</button>`}
          ${isFinding && !c.action && html`<div class="muted" style="margin-top:6px">The follow-up inspection becomes available after the corrective action.</div>`}
          <div class="muted" style="margin-top:8px;font-size:12px">No physical drone, imagery or thermal data. Inspection results are recorded by the operator.</div>
        </div>
      </div>

      <div class="stack">
        <div class="card"><h2>Corrective action <span class="r muted">technician</span></h2>
          ${c.action ? html`<div><b>${c.technician}</b> <span class="muted">· ${fmtWall(c.action.wall_ts)}${c.action.data_ts ? ` (replay time ${fmtT(c.action.data_ts)})` : ""}</span><p>${c.action.text}</p></div>`
            : role !== "technician" ? html`<div class="muted">Switch the demo role to <b>Technician</b> (top right) to record the corrective action.</div>`
            : html`<div class="stack"><div class="muted">Acting as <b>${names.technician}</b></div>
                <textarea placeholder=${isFinding ? "What was done (e.g. pallets removed from the exit, area marked)" : "What was found and done (e.g. isolated the cable-tray circuit, removed burnt insulation)"} value=${action} onInput=${e => setAction(e.target.value)}></textarea>
                <button class="btn primary" disabled=${action.trim().length < 10 || c.status !== "OPEN"} onClick=${() => post("action", { technician: names.technician, action })}>Record corrective action</button></div>`}
        </div>
        <div class="card"><h2>Independent verification <span class="r muted">verifier</span></h2>
          ${c.verification?.approved ? html`<div><b>${c.verifier}</b> <span class="muted">approved · ${fmtWall(c.verification.wall_ts)}</span><p>${c.verification.note || "—"}</p></div>`
            : c.status !== "ACTION_RECORDED" ? html`<div class="muted">Available after the technician records the corrective action.${c.verification && !c.verification.approved ? html`<br/>Last verification was rejected by ${c.verification.by}: ${c.verification.note}` : ""}</div>`
            : role !== "verifier" ? html`<div class="muted">Switch the demo role to <b>Verifier</b>. The verifier must be a different person from the technician.</div>`
            : html`<div class="stack"><div class="muted">Acting as <b>${names.verifier}</b></div>
                <textarea placeholder="Verification note" value=${note} onInput=${e => setNote(e.target.value)}></textarea>
                <div class="row"><button class="btn primary" onClick=${() => post("verify", { verifier: names.verifier, approve: true, note })}>Approve</button>
                <button class="btn danger" onClick=${() => post("verify", { verifier: names.verifier, approve: false, note: note || "Rejected" })}>Reject</button></div></div>`}
        </div>
        <div class="card"><h2>${isFinding ? "Closure check" : "Stabilization check"} <span class="r muted">${isFinding ? "follow-up inspection (simulated)" : "system, live readings"}</span></h2>
          <div class="muted" style="font-size:12.5px">${c.stabilization?.criterion || (isFinding
            ? "A follow-up drone inspection of the same checkpoint, flown after the corrective action, must confirm the condition is cleared."
            : "15 consecutive minutes of LIVE readings (at least 2 nodes) with risk NORMAL and fire likelihood < 20 %, after the corrective action. Gaps and held/repeated values do not count. Prototype rule, not a validated industrial standard.")}</div>
          ${c.stabilization && html`<div class="row" style="margin-top:10px"><span class=${`pill ${c.stabilization.passed ? "ok" : "bad"}`}>${c.stabilization.passed ? "PASSED" : isFinding ? "NOT YET CONFIRMED" : "AWAITING STABILIZATION"}</span>
            ${!isFinding && html`<span>${c.stabilization.measured_minutes} / ${c.stabilization.required_minutes} min of live normal readings</span><span class="muted">checked up to ${fmtT(c.stabilization.checked_up_to)}</span>`}</div>
            ${c.stabilization.note && html`<div class="muted" style="margin-top:6px;font-size:12.5px">${c.stabilization.note}</div>`}`}
          ${c.status === "VERIFIED" && html`<div class="row" style="margin-top:10px"><button class="btn primary" onClick=${() => post("close-check")}>Run closure check</button></div>`}
          ${c.status === "CLOSED" && html`<div class="banner info" style="margin-top:10px">✓ Closed with 3 confirmations: technician, independent verifier, and ${isFinding ? "a follow-up inspection (simulated evidence)" : "live measured readings"}.</div>`}
          ${!isFinding && c.stabilization && !c.stabilization.passed && c.stabilization.non_live_ticks_after_action > 0 && html`<div class="banner info" style="margin-top:10px">ⓘ Why the case stays open: in this dataset the recording repeats its last values for 20–45 min after each experiment (likely the ventilation phase), and the next experiment starts soon after. Repeated values are not measurements, so AEROGUARD refuses to close the case on data it cannot trust.</div>`}
        </div>
        <div class="card"><h2>Audit trail</h2><${Timeline} events=${trail} compact/></div>
      </div>
    </div>
  </div>`;
}

function SimBanner() {
  return html`<div class="banner sim">◈ <div><b>Simulated drone mission.</b> No physical drone connected · no imagery or thermal data captured · no validated thermal or visual detection model. Findings are <b>illustrative</b> and recorded by the operator.</div></div>`;
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
  const shown = active || drone.missions.find(m => m.status === "COMPLETED");

  return html`<div class="page">
    <${SimBanner}/>
    <div class="grid g-main">
      <div class="card"><h2>Facility schematic · route and drone position <span class="r muted">${active ? `${MODE_LABEL[active.mode]} in progress` : "drone on dock"}</span></h2>
        <${HallMap} facility=${ctx.facility} nodes=${ctx.state?.latest?.nodes || {}} fireNodes=${ctx.state?.latest?.decision?.fire_nodes} drone=${drone} mission=${shown}/>
      </div>
      <div class="stack">
        <div class="card"><h2>Start a preventive patrol</h2>
          <div class="stack"><select class="in" value=${route} onChange=${e => setRoute(e.target.value)}>
            ${drone.routes.map(r => html`<option value=${r.id}>${r.label} (${r.checkpoints.length} checkpoints)</option>`)}</select>
            <button class="btn primary" disabled=${!!active} onClick=${() => call("/api/drone/missions", { route_id: route })}>▶ Start patrol now</button>
            ${active && html`<div class="muted">A mission is in flight. Pause or cancel it to start another.</div>`}</div></div>
        ${active && html`<div class="card"><h2>Mission ${active.id} <span class="r"><span class=${`pill ${active.status === "PAUSED" ? "HIGH" : "WATCH"}`}>${active.status.replace("_", " ")}</span></span></h2>
          <div><b>${MODE_LABEL[active.mode]}</b> · ${active.label} · <span class="muted">${ORIGIN_LABEL[active.origin]}</span></div>
          <div class="bar"><i style=${`width:${Math.round(active.progress * 100)}%`}></i></div>
          <div class="muted">${active.current || "Taking off"} · ${Math.round(active.progress * 100)} %</div>
          <div class="row" style="margin-top:8px">${active.status === "PAUSED"
            ? html`<button class="btn" onClick=${() => call(`/api/drone/missions/${active.id}/actions/resume`)}>▶ Resume</button>`
            : html`<button class="btn" onClick=${() => call(`/api/drone/missions/${active.id}/actions/pause`)}>❚❚ Pause</button>`}
            <button class="btn danger" onClick=${() => call(`/api/drone/missions/${active.id}/actions/cancel`)}>✕ Cancel mission</button></div></div>`}
        ${awaiting.length > 0 && html`<div class="card" style="border-color:var(--high)"><h2>Awaiting your approval</h2>
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
      ${form && html`<div class="card" style="margin-top:12px;background:var(--bg2)"><h2>Record an illustrative finding · ${form.label}</h2>
        <div class="grid g3"><label class="f">Type<select class="in" value=${ftype} onChange=${e => setFtype(e.target.value)}>
          ${Object.entries(drone.finding_types).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select></label>
          <label class="f">Severity<select class="in" value=${sev} onChange=${e => setSev(e.target.value)}>${drone.severities.map(s => html`<option>${s}</option>`)}</select></label>
          <label class="f">Note<input type="text" value=${note} onInput=${e => setNote(e.target.value)} placeholder="What the inspector would see"/></label></div>
        <div class="row" style="margin-top:10px"><button class="btn primary" onClick=${async () => { const r = await call(`/api/drone/missions/${form.mission}/findings`, { checkpoint: form.checkpoint, type: ftype, severity: sev, note }); if (r) setForm(null); }}>Save finding</button>
          <button class="btn ghost" onClick=${() => setForm(null)}>Cancel</button>
          <span class="muted">Recorded by the operator from a simulated mission. Not an automatic detection.</span></div></div>`}
    </div>`}

    <div class="grid g2">
      <div class="card"><h2>Preventive patrol schedule <span class="r"><span class="pill sim">SIMULATED SCHEDULER</span></span></h2>
        <div class="muted" style="font-size:12.5px;margin-bottom:8px">${drone.scheduler_note}</div>
        <table class="t"><thead><tr><th>Route</th><th>Every</th><th>Next patrol</th><th>Active</th></tr></thead><tbody>
          ${drone.schedules.map(s => html`<tr><td><b>${rl(s.route_id)}</b></td>
            <td><select class="in" style="width:auto;padding:4px 8px" value=${s.every_minutes} onChange=${e => call(`/api/drone/schedules/${s.id}`, { every_minutes: +e.target.value })}>
              ${[...new Set([...freqs, s.every_minutes])].sort((a, b) => a - b).map(f => html`<option value=${f}>${f < 60 ? `${f} min` : f === 1440 ? "24 h" : `${f / 60} h`}</option>`)}</select></td>
            <td>${s.enabled ? inMin(s.next_due) : "—"} <button class="btn sm ghost" onClick=${() => call(`/api/drone/schedules/${s.id}`, { start_in_minutes: 1 })}>in 1 min</button></td>
            <td><button class=${`btn sm ${s.enabled ? "" : "ghost"}`} onClick=${() => call(`/api/drone/schedules/${s.id}`, { enabled: !s.enabled })}>${s.enabled ? "On" : "Off"}</button></td></tr>`)}</tbody></table></div>
      <div class="card"><h2>Inspection findings <span class="r"><span class="pill sim">ILLUSTRATIVE</span></span></h2>
        ${drone.findings.length ? html`<table class="t"><tbody>${drone.findings.map(f => html`<tr>
          <td><b>${f.type_label}</b><div class="muted">${f.checkpoint_label} · ${f.note || "—"}</div></td>
          <td><span class=${`pill ${f.severity === "HIGH" ? "CRITICAL" : f.severity === "MEDIUM" ? "HIGH" : "WATCH"}`}>${f.severity}</span></td>
          <td class="num">${f.case_id ? html`<a class="btn sm" href=${`#/cases/${f.case_id}`}>${f.case_id} →</a>`
            : html`<button class="btn sm primary" onClick=${async () => { const c = await call(`/api/findings/${f.id}/case`, { opened_by: "operator" }); if (c) location.hash = `#/cases/${c.id}`; }}>Open Safety Case</button>`}</td></tr>`)}</tbody></table>`
          : html`<div class="empty">No finding yet. Inspect checkpoints during a patrol, then record a finding or mark them clear.</div>`}</div>
    </div>

    <div class="card"><h2>Mission history</h2>
      ${drone.missions.length ? html`<table class="t"><thead><tr><th>Mission</th><th>Type</th><th>Trigger</th><th>Checkpoints</th><th>Status</th><th>Findings</th><th>Case</th></tr></thead><tbody>
        ${drone.missions.map(m => html`<tr><td><b>${m.id}</b><div class="muted">${fmtWall(m.created_at)}</div></td><td>${MODE_LABEL[m.mode]}</td><td class="muted">${ORIGIN_LABEL[m.origin]}</td>
          <td class="muted">${m.checkpoints.map(c => c.label).join(" → ")}</td><td><span class=${`pill ${m.status === "COMPLETED" ? "ok" : m.status === "CANCELLED" ? "pending" : "WATCH"}`}>${m.status.replace("_", " ")}</span></td>
          <td class="num">${m.findings.length}</td><td>${m.case_id ? html`<a href=${`#/cases/${m.case_id}`}>${m.case_id}</a>` : "—"}</td></tr>`)}</tbody></table>`
        : html`<div class="empty">No mission flown yet.</div>`}</div>
  </div>`;
}

function Cases({ ctx }) {
  const { cases } = ctx;
  return html`<div class="page"><div class="card"><h2>Digital Safety Cases</h2>
    ${cases.length ? html`<table class="t"><thead><tr><th>Case</th><th>Status</th><th>Severity</th><th>Zone</th><th>Recorded time opened</th><th>Technician</th><th>Verifier</th></tr></thead>
      <tbody>${cases.map(c => html`<tr class="click" onClick=${() => location.hash = `#/cases/${c.id}`}>
        <td><b>${c.id}</b></td><td><span class=${`pill ${c.status}`}>${c.status.replace("_", " ")}</span></td><td><span class=${`pill ${c.severity}`}>${c.severity}</span></td>
        <td>${c.zone}</td><td class="mono">${fmtT(c.opened_data_ts, true)}</td><td>${c.technician || "—"}</td><td>${c.verifier || "—"}</td></tr>`)}</tbody></table>`
      : html`<div class="empty">No case yet. Replay a recorded fire in <a href="#/monitor">Live monitoring</a>: a case opens when two sensor nodes confirm a fire signature.</div>`}
  </div></div>`;
}

function Timeline({ events, compact }) {
  if (!events.length) return html`<div class="empty">No events recorded yet</div>`;
  const title = (e) => ({
    risk_level_changed: `Risk ${e.payload.from} → ${e.payload.to}`, alert: `Alert ${e.payload.level}`, case_opened: "Safety Case opened",
    case_escalated: "Case escalated", technician_action: "Corrective action recorded", verification_approved: "Independent verification approved",
    verification_rejected: "Verification rejected", stabilization_check: `Stabilization check ${e.payload.passed ? "passed" : "not yet satisfied"}`,
    case_closed: "Case closed", replay_loaded: `Recording loaded: ${e.payload.event_id}`, demo_reset: "Demo reset",
    replay_auto_paused: "Replay paused for the response",
    mission_created: `Drone mission ${e.payload.mission} created (${(e.payload.mode || "").toLowerCase().replace("_", "-")})`,
    mission_approve: `Drone flight approved (${e.payload.mission})`, mission_pause: `Drone mission paused (${e.payload.mission})`,
    mission_resume: `Drone mission resumed (${e.payload.mission})`, mission_cancel: `Drone mission cancelled (${e.payload.mission})`,
    mission_completed: `Drone mission completed (${e.payload.mission})`, checkpoint_inspected: `Checkpoint inspected: ${e.payload.label}`,
    inspection_finding: `Illustrative finding: ${e.payload.type} at ${e.payload.checkpoint}`, checkpoint_clear: `Checkpoint marked clear: ${e.payload.checkpoint}`,
    closure_check: `Closure check ${e.payload.passed ? "passed" : "not yet satisfied"}`, patrol_schedule_set: "Patrol schedule updated",
    drone_requested: "Drone inspection requested", drone_approved: "Drone flight approved", drone_in_flight: "Drone in flight", drone_completed: "Drone inspection completed",
  }[e.kind] || e.kind);
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
        <div class="row" style="margin-top:12px"><span class="pill pending">HEDERA: PENDING</span></div>
        <div class="muted" style="font-size:12.5px;margin-top:6px">${p.hedera.note}. No blockchain transaction is shown because none has been made.</div></div>
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
          ${f.open_cases.length > 0 && html`<div><b>Open Safety Cases</b><div class="muted">${f.open_cases.map(c => `${c.id} (${c.status})`).join(", ")}</div></div>`}
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
    title: "Scenario 1 · Preventive drone inspection",
    tag: "SIMULATED DRONE · ILLUSTRATIVE FINDING",
    steps: [
      { title: "The preventive patrol plan", go: "#/drone",
        text: "AEROGUARD does not wait for an alarm. The drone flies predefined routes on a schedule (here: full patrol every hour). The scheduler is simulated and runs while the server runs." },
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
      { title: "Open a follow-up Safety Case", label: "Open Safety Case",
        act: async (ctx, d) => { const c = await api(`/api/findings/${d.finding}/case`, { opened_by: "operator" }); location.hash = `#/cases/${c.id}`; return { case: c.id }; },
        done: (ctx, d) => !!d.case,
        text: "The finding becomes a traceable Safety Case with its own evidence and audit trail." },
      { title: "Assign the corrective action", label: "Record action as technician",
        act: async (ctx, d) => { ctx.setRole("technician"); await api(`/api/cases/${d.case}/action`, { technician: ctx.names.technician, action: "Pallets removed from the east exit; floor marking repainted." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.action,
        text: "The technician records what was done. The demo role switches to Technician (top right)." },
      { title: "Independent verification", label: "Approve as verifier",
        act: async (ctx, d) => { ctx.setRole("verifier"); await api(`/api/cases/${d.case}/verify`, { verifier: ctx.names.verifier, approve: true, note: "Exit checked on site." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.verification?.approved,
        text: "A different person must approve. The system refuses self-verification." },
      { title: "Follow-up inspection and closure", label: "Fly follow-up, mark clear, close",
        act: async (ctx, d) => {
          if (!d.followup) { if (ctx.drone?.active) throw new Error("Wait until the patrol returns to its dock, then try again.");
            const m = await api(`/api/cases/${d.case}/inspection`, {}); return { followup: m.id }; }
          const m = ctx.drone?.missions.find(x => x.id === d.followup);
          if (m?.status !== "COMPLETED") throw new Error("The follow-up drone is still flying. Try again when it has landed.");
          await api(`/api/drone/missions/${d.followup}/clear`, { checkpoint: "CP-EE" });
          await api(`/api/cases/${d.case}/close-check`, {}); return {}; },
        done: (ctx, d) => ctx.cases.find(c => c.id === d.case)?.status === "CLOSED",
        text: "Press once to send the follow-up drone, and again after it lands to record 'clear' and run the closure check. Closed with simulated inspection evidence, clearly labelled." },
    ],
  },
  sensor: {
    title: "Scenario 2 · Real-data AI early warning",
    tag: "REAL RECORDED DATA · HELD-OUT AI MODEL",
    steps: [
      { title: "A normal facility", go: "#/",
        text: "The Overview answers: is my facility safe, what needs attention, what should I do next. Nothing is replaying yet." },
      { title: "Choose the authentic Cable#4 recording", go: "#/monitor", label: "Load Cable#4",
        act: async () => { await api("/api/replay/load", { event_id: "Cable#4" }); await api("/api/replay/speed", { speed: 60 }); return {}; },
        done: (ctx) => ctx.state?.event_id === "Cable#4",
        text: "A real cable fire recorded in an industrial hall (Otto von Guericke University dataset). It is analysed by a model that was trained without this event." },
      { title: "Start the replay", go: "#/monitor", label: "Play at 60×",
        act: async () => { await api("/api/replay/play", {}); return {}; },
        done: (ctx) => !!sensorCase(ctx),
        text: "Each 10-second tick, the model scores only readings already played. Watch the fire likelihood rise with CO and particles. The replay pauses itself when a Safety Case opens." },
      { title: "Risk classification", go: "#/monitor",
        text: "Two sensor nodes agree on a fire signature for 30 s: CRITICAL. On the 32 recorded events, this AI alarmed earlier than a calibrated particle threshold on 14 of 16 fires (median 195 s), with similar false-alarm performance." },
      { title: "The Safety Case opened automatically",
        act: async (ctx) => { const c = sensorCase(ctx); location.hash = `#/cases/${c.id}`; return { case: c.id }; }, label: "Open the case",
        done: (ctx, d) => !!d.case,
        text: "The case holds the sensor evidence at the moment of the alert and requested a targeted drone inspection that waits for operator approval." },
      { title: "Approve the targeted inspection", label: "Approve drone flight",
        act: async (ctx, d) => { const m = ctx.drone?.missions.find(x => x.case_id === d.case && x.status === "AWAITING_APPROVAL");
          if (!m) throw new Error("No inspection waiting for approval for this case."); await api(`/api/drone/missions/${m.id}/actions/approve`, {}); return { mission: m.id }; },
        done: (ctx, d) => !!d.mission,
        text: "The operator stays in control: the drone only flies after approval. Simulated mission." },
      { title: "Corrective action", label: "Record action as technician",
        act: async (ctx, d) => { ctx.setRole("technician"); await api(`/api/cases/${d.case}/action`, { technician: ctx.names.technician, action: "Isolated the cable-tray circuit near N6/N7 and removed burnt insulation." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.action, text: "The technician records the intervention." },
      { title: "Independent verification", label: "Approve as verifier",
        act: async (ctx, d) => { ctx.setRole("verifier"); await api(`/api/cases/${d.case}/verify`, { verifier: ctx.names.verifier, approve: true, note: "Checked on site." }); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.verification?.approved, text: "A different person approves." },
      { title: "Collect post-action readings", label: "Resume replay", go: "#/monitor",
        act: async () => { await api("/api/replay/speed", { speed: 120 }); await api("/api/replay/play", {}); return {}; },
        done: (ctx) => !!ctx.state?.finished,
        text: "The replay continues with the real recording after the fire, until just before the next experiment in the dataset." },
      { title: "Stabilization check", label: "Run closure check",
        act: async (ctx, d) => { location.hash = `#/cases/${d.case}`; await api(`/api/cases/${d.case}/close-check`, {}); return {}; },
        done: (ctx, d) => !!ctx.cases.find(c => c.id === d.case)?.stabilization,
        text: "The case should close only after 15 min of LIVE normal readings. Here the recording repeats its last values after the fire, so AEROGUARD correctly refuses to close and explains why." },
      { title: "Equipment Passport", go: "#/passport", text: "The zone's history now includes the case, the inspection and every decision, with a local integrity chain (Hedera anchoring pending)." },
      { title: "Black Box", go: "#/blackbox", text: "Every event in order, labelled by source: recorded data, model output, risk engine, human action (demo role), simulated drone." },
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
    <div class="row between"><b>${sc.title}</b><button class="btn sm ghost" onClick=${() => setDemo(null)}>✕</button></div>
    <div class="tagline">${sc.tag}</div>
    <div class="gstep">Step ${demo.i + 1} of ${sc.steps.length}</div>
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
    <h2>Start guided demo</h2>
    <p class="muted">Two scenarios. Every step uses the real application; you can also click around freely at any time.</p>
    <div class="grid g2">
      <button class="ev" onClick=${() => onPick("patrol")}><b>1 · Preventive drone inspection</b><small>Scheduled patrol, route, checkpoints, an illustrative finding, Safety Case, corrective action, verification, follow-up inspection.</small><span class="pill sim">simulated drone</span></button>
      <button class="ev" onClick=${() => onPick("sensor")}><b>2 · Real-data AI early warning</b><small>Authentic Cable#4 recording, held-out AI model, CRITICAL risk, automatic Safety Case, targeted inspection, verification, stabilization refusal, Passport, Black Box.</small><span class="pill rec">real recorded data</span></button>
    </div>
    <div class="row" style="margin-top:12px"><button class="btn sm ghost" onClick=${async () => { if (confirm("Clear all demo cases, missions and events before starting?")) { await api("/api/demo/reset", {}); location.reload(); } }}>Start from a clean slate</button><span class="grow"></span><button class="btn ghost" onClick=${onClose}>Close</button></div>
  </div></div>`;
}

// ------------------------------------------------------------------ app shell
const NAV = [
  ["#/", "◎", "Overview"], ["#/monitor", "▶", "Live Monitoring"], ["#/drone", "✈", "Drone Operations"], ["#/cases", "◆", "Safety Cases"],
  ["#/passport", "▤", "Equipment Passport"], ["#/blackbox", "◷", "Black Box"], ["#/firepack", "✚", "Emergency Fire Pack"], ["#/evidence", "✓", "AI Evidence"],
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
  const [demo, setDemo] = useState(null);
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
  if (route.startsWith("/cases/")) { const id = route.split("/")[2]; page = html`<${CaseDetail} id=${id} ctx=${ctx} key=${id}/>`; title = `Safety Case ${id}`; sub = "Evidence, response workflow and audit trail"; }
  else ({
    "/": () => { page = html`<${Overview} ctx=${ctx}/>`; title = "Overview"; sub = "Is my facility safe? What needs attention? What should I do next?"; },
    "/monitor": () => { page = html`<${Monitor} ctx=${ctx}/>`; title = "Live Monitoring"; sub = "Real recorded sensor data, replayed and analysed by the trained model"; },
    "/drone": () => { page = html`<${DroneOps} ctx=${ctx}/>`; title = "Drone Operations"; sub = "Preventive patrols and alert-triggered inspections (simulated drone)"; },
    "/cases": () => { page = html`<${Cases} ctx=${ctx}/>`; title = "Safety Cases"; sub = "Open investigations, corrective actions and independent verification"; },
    "/passport": () => { page = html`<${Passport} ctx=${ctx}/>`; title = "Equipment Passport"; sub = "History and integrity of the monitored zone"; },
    "/blackbox": () => { page = html`<${BlackBox} ctx=${ctx}/>`; title = "Black Box"; sub = "Chronological record of everything that happened"; },
    "/firepack": () => { page = html`<${FirePack} ctx=${ctx}/>`; title = "Emergency Fire Pack"; sub = "Emergency information for authorized responders"; },
    "/evidence": () => { page = html`<${Evidence} ctx=${ctx}/>`; title = "AI Evidence"; sub = "What the real data supports, and what it does not"; },
  }[route] || (() => { page = html`<div class="page"><div class="empty">Page not found. <a href="#/">Back to Overview</a></div></div>`; title = "Not found"; }))();

  return html`<div class="shell">
    <aside class="side">
      <div class="brand"><svg viewBox="0 0 32 32"><path d="M16 2 4 7v8c0 7.5 5.1 13.6 12 15 6.9-1.4 12-7.5 12-15V7z" fill="#f59e0b"/><path d="M11 17l4 4 7-9" stroke="#1a1205" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div><b>AEROGUARD</b><span>TRUST · CONTROL ROOM</span></div></div>
      <nav class="nav">${NAV.map(([h, i, t]) => html`<a href=${h} class=${(h === "#/" ? hash === "#/" || hash === "" : hash.startsWith(h)) ? "on" : ""}>
        <span class="ico">${i}</span>${t}${t === "Safety Cases" && open ? html`<span class="badge">${open}</span>` : ""}${t === "Drone Operations" && awaiting ? html`<span class="badge warn">${awaiting}</span>` : ""}</a>`)}</nav>
      <div class="foot">Prototype · sensor data = historical replay of real recordings (Industrial Hall dataset, CC BY 4.0) · drone simulated · demo roles · Hedera pending
        <div style="margin-top:8px"><button class="btn sm ghost" onClick=${async () => { if (confirm("Clear all demo cases, missions and events?")) { await api("/api/demo/reset", {}); setDemo(null); location.hash = "#/"; refreshAll(); } }}>Reset demo</button></div></div>
    </aside>
    <main class="main">
      <div class="top"><div><h1>${title}</h1><div class="sub">${sub}</div></div><span class="grow"></span>
        ${!online && html`<span class="pill bad">backend offline: start the server</span>`}
        <button class="btn primary" onClick=${() => setPicker(true)}>▶ Start Guided Demo</button>
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
