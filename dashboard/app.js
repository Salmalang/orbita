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
const LEVEL_TEXT = { NORMAL: "NORMAL", WATCH: "WATCH", HIGH: "HIGH", CRITICAL: "CRITICAL", NO_DATA: "NO DATA" };
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
function HallMap({ facility, nodes, fireNodes, onPick, picked, showExits = true }) {
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
    </svg>
    <div class="legend"><span><i style="background:#22c55e"></i>normal</span><span><i style="background:#3b82f6"></i>nuisance-like</span>
      <span><i style="background:#f59e0b"></i>fire signal</span><span><i style="background:#ef4444"></i>confirmed fire node</span><span><i style="background:#334155"></i>no data yet</span></div>
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
function Overview({ ctx }) {
  const { facility, state, cases, alerts } = ctx;
  const dec = state?.latest?.decision;
  const nodes = state?.latest?.nodes || {};
  const reporting = Object.values(nodes).length ? (dec ? dec.healthy_nodes : 0) : 0;
  const open = cases.filter(c => c.status !== "CLOSED");
  return html`<div class="page">
    <div class="banner info">ⓘ <div><b>${facility?.site}</b>. ${facility?.illustrative_note}</div></div>
    <div class="grid g4">
      <div class="card kpi"><div class="v"><span class=${`pill ${dec?.level || "NO_DATA"}`} style="font-size:20px;padding:4px 14px">${LEVEL_TEXT[dec?.level || "NO_DATA"]}</span></div><div class="l">Zone risk · ${facility?.name}</div></div>
      <div class="card kpi"><div class="v">${reporting}<span class="dim" style="font-size:18px"> / ${facility?.nodes.length || 9}</span></div><div class="l">Sensor nodes reporting</div></div>
      <div class="card kpi"><div class="v" style=${open.length ? "color:var(--crit)" : ""}>${open.length}</div><div class="l">Open Safety Cases</div></div>
      <div class="card kpi"><div class="v">${alerts.length}</div><div class="l">Alerts in this session</div></div>
    </div>
    <div class="grid g-main">
      <div class="card"><h2>Production hall · live view <span class="r"><span class="pill rec">● HISTORICAL REPLAY</span></span></h2>
        <${HallMap} facility=${facility} nodes=${nodes} fireNodes=${dec?.fire_nodes}/>
        <div class="row" style="margin-top:12px"><a class="btn primary" href="#/monitor">▶ Open live monitoring</a>
          <span class="muted">${state?.event_id ? `Replaying ${state.event_id} · recorded ${fmtT(state.cursor, true)}` : "No recording loaded yet"}</span></div>
      </div>
      <div class="stack">
        <${RiskBanner} decision=${dec} compact/>
        <div class="card"><h2>Safety Cases awaiting action</h2>
          ${open.length ? html`<table class="t"><tbody>${open.map(c => html`<tr class="click" onClick=${() => location.hash = `#/cases/${c.id}`}>
            <td><b>${c.id}</b><div class="muted">${c.zone}</div></td><td><span class=${`pill ${c.status}`}>${c.status.replace("_", " ")}</span></td>
            <td class="num muted">${fmtT(c.opened_data_ts)}</td></tr>`)}</tbody></table>` : html`<div class="empty">No open case</div>`}
        </div>
        <div class="card"><h2>Recent alerts</h2>
          ${alerts.length ? html`<div class="stack">${alerts.slice(-5).reverse().map(a => html`<div class="row between">
            <span><span class=${`pill ${a.payload.level}`}>${a.payload.level}</span> <span class="muted">${a.payload.replay_event || ""}</span></span>
            <span class="mono dim">${fmtT(a.data_ts)}</span></div>`)}</div>` : html`<div class="empty">No alert yet</div>`}
        </div>
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
          series=${[{ label: "max P(fire) across nodes", data: S("max_p_fire"), color: "#ef4444", fill: "rgba(239,68,68,.08)" },
                    { label: "max P(nuisance)", data: S("max_p_nuisance"), color: "#3b82f6" }]}
          thresholds=${[{ label: "fire threshold (0.95)", value: 0.95, color: "rgba(255,255,255,.35)" }]}/>
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
          <table class="t"><thead><tr><th>Node</th><th class="num">P(fire)</th><th class="num">P(nuis.)</th><th class="num">CO ppm</th><th class="num">particles</th></tr></thead>
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

const STEPS = [
  ["Alert", "Risk engine"], ["Case opened", "System"], ["Drone check", "Simulated"],
  ["Corrective action", "Technician"], ["Independent check", "Verifier"], ["Stabilization", "System, measured"],
];

function CaseDetail({ id, ctx }) {
  const { role, names, toast, refresh } = ctx;
  const [c, setC] = useState(null);
  const [trail, setTrail] = useState([]);
  const [action, setAction] = useState("");
  const [note, setNote] = useState("");
  const load = useCallback(async () => {
    const [cc, tl] = await Promise.all([api(`/api/cases/${id}`), api(`/api/timeline?case_id=${id}`)]);
    setC(cc); setTrail(tl);
  }, [id]);
  usePoll(load, 2000, [id]);
  if (!c) return html`<div class="page"><div class="empty">Loading case…</div></div>`;
  const post = async (path, body) => { try { setC(await api(`/api/cases/${id}/${path}`, body ?? {})); await load(); await refresh(); } catch (e) { toast(e.message, true); } };
  const ds = c.drone?.status;
  const done = [true, true, ds === "COMPLETED", !!c.action, !!c.verification?.approved, c.status === "CLOSED"];
  const cur = done.indexOf(false);
  const nextDrone = !ds ? "REQUESTED" : { REQUESTED: "APPROVED", APPROVED: "IN_FLIGHT", IN_FLIGHT: "COMPLETED" }[ds];
  const droneLabel = { REQUESTED: "Request drone inspection", APPROVED: "Approve flight (operator)", IN_FLIGHT: "Launch (simulated)", COMPLETED: "Mark inspection complete" };
  const ev = c.evidence?.nodes || {};

  return html`<div class="page">
    <div class="row between">
      <div class="row"><a href="#/cases" class="btn sm ghost">← Cases</a><h2 style="margin:0;font-size:20px">${c.id}</h2>
        <span class=${`pill ${c.status}`}>${c.status.replace("_", " ")}</span><span class=${`pill ${c.severity}`}>${c.severity}</span>
        ${c.escalations ? html`<span class="pill bad">escalated ×${c.escalations}</span>` : ""}</div>
      <span class="muted">Zone ${c.zone} · opened at recorded time ${fmtT(c.opened_data_ts, true)} · replay ${c.replay_event}</span>
    </div>
    <div class="steps">${STEPS.map(([t, w], i) => html`<div class=${`step ${done[i] ? "done" : i === cur ? "cur" : ""}`}>
      <div class="n">STEP ${i + 1} · ${w.toUpperCase()}</div><b>${done[i] ? "✓ " : ""}${t}</b></div>`)}</div>

    <div class="grid g-main">
      <div class="stack">
        <div class="card"><h2>AI findings at opening</h2>
          <ul style="margin:0 0 10px;padding-left:18px">${c.findings.map(f => html`<li>${f}</li>`)}</ul>
          <table class="t"><thead><tr><th>Node</th><th class="num">P(fire)</th><th class="num">P(nuisance)</th><th class="num">CO ppm</th><th class="num">CO₂ ppm</th><th class="num">particles</th><th class="num">temp °C</th></tr></thead>
            <tbody>${Object.entries(ev).sort((a, b) => b[1].p_fire - a[1].p_fire).map(([k, v]) => html`<tr>
              <td>${ctx.facility?.nodes.find(n => n.id === k)?.label || k} ${c.fire_nodes.includes(k) && html`<span class="pill CRITICAL">fire</span>`}</td>
              <td class="num">${pct(v.p_fire)}</td><td class="num">${pct(v.p_nuisance)}</td><td class="num">${num(v.readings.co_ppm, 2)}</td>
              <td class="num">${num(v.readings.co2_ppm, 0)}</td><td class="num">${num(v.readings.pm_total, 0)}</td><td class="num">${num(v.readings.temperature_c, 1)}</td></tr>`)}</tbody></table>
          <div class="muted" style="margin-top:8px;font-size:12px">Evidence = recorded sensor readings and model outputs at the moment the case opened (model ${c.evidence?.model}).</div>
        </div>
        <div class="card"><h2>Recommended inspection</h2><div>${c.recommended_inspection}</div>
          <div class="banner info" style="margin-top:10px">Certified fire alarms and emergency shutdown systems act independently of AEROGUARD. This case supports the response; it never replaces them.</div></div>

        <div class="card"><h2>Drone inspection <span class="r"><span class="pill sim">SIMULATED WORKFLOW</span></span></h2>
          <div class="banner sim">No drone hardware is connected. The steps below demonstrate the workflow; no footage or temperature is captured or invented.</div>
          <div class="row" style="margin:12px 0">
            ${["REQUESTED", "APPROVED", "IN_FLIGHT", "COMPLETED"].map(s => html`<span class=${`pill ${c.drone?.history?.some(h => h.step === s) ? "sim" : "pending"}`}>${s.replace("_", " ")}</span>`)}
            <span class="grow"></span>
            ${nextDrone && c.status !== "CLOSED" && html`<button class="btn" onClick=${() => post("drone", { step: nextDrone, actor: role === "technician" ? names.technician : role === "verifier" ? names.verifier : "operator" })}>${droneLabel[nextDrone]}</button>`}
          </div>
          ${ds === "COMPLETED" && html`<div class="grid g2"><div class="muted">${c.drone.findings}</div>
            <figure style="margin:0"><img class="fig" src="/api/reference-image" alt="Reference thermal image" style="background:#000"/>
              <figcaption class="muted" style="font-size:11.5px;margin-top:4px"><b>Illustrative reference only, not this hall:</b> thermal image of an induction motor with a stator short-circuit, Najafi et al., Mendeley Data, doi:10.17632/m4sbt8hbvk.3 (CC BY 4.0).</figcaption></figure></div>`}
        </div>
      </div>

      <div class="stack">
        <div class="card"><h2>Corrective action <span class="r muted">technician</span></h2>
          ${c.action ? html`<div><b>${c.technician}</b> <span class="muted">· recorded ${fmtWall(c.action.wall_ts)} (replay time ${fmtT(c.action.data_ts)})</span><p>${c.action.text}</p></div>`
            : role !== "technician" ? html`<div class="muted">Switch the demo role to <b>Technician</b> (top right) to record the corrective action.</div>`
            : html`<div class="stack"><div class="muted">Acting as <b>${names.technician}</b></div>
                <textarea placeholder="What was found and done (e.g. isolated the cable-tray circuit, removed burnt insulation, checked adjacent cabinets)" value=${action} onInput=${e => setAction(e.target.value)}></textarea>
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
        <div class="card"><h2>Stabilization check <span class="r muted">system, on measured data</span></h2>
          <div class="muted" style="font-size:12.5px">${c.stabilization?.criterion || "15 consecutive minutes of LIVE readings (at least 2 nodes) with risk NORMAL and P(fire) < 0.2, after the corrective action. Gaps and held/repeated values do not count. Prototype rule, not a validated industrial standard."}</div>
          ${c.stabilization && html`<div class="row" style="margin-top:10px"><span class=${`pill ${c.stabilization.passed ? "ok" : "bad"}`}>${c.stabilization.passed ? "PASSED" : "AWAITING STABILIZATION"}</span>
            <span>${c.stabilization.measured_minutes} / ${c.stabilization.required_minutes} min measured normal</span><span class="muted">checked up to ${fmtT(c.stabilization.checked_up_to)}</span></div>
            ${c.stabilization.note && html`<div class="muted" style="margin-top:6px;font-size:12.5px">${c.stabilization.note}</div>`}`}
          ${c.status === "VERIFIED" && html`<div class="row" style="margin-top:10px"><button class="btn primary" onClick=${() => post("stabilization")}>Run stabilization check</button>
            <span class="muted">If not enough data yet, continue the replay and check again.</span></div>`}
          ${c.status === "CLOSED" && html`<div class="banner info" style="margin-top:10px">✓ Closed with 3 confirmations: technician, independent verifier, and the measured readings.</div>`}
          ${c.stabilization && !c.stabilization.passed && c.stabilization.non_live_ticks_after_action > 0 && html`<div class="banner info" style="margin-top:10px">ⓘ In this dataset the recording holds its last values for 20–45 min after each experiment (likely the ventilation phase), and the next experiment starts soon after. Held values are not measurements, so AEROGUARD keeps the case open rather than closing it on data it cannot trust.</div>`}
        </div>
        <div class="card"><h2>Audit trail</h2><${Timeline} events=${trail} compact/></div>
      </div>
    </div>
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
const NAV = [
  ["#/", "◎", "Overview"], ["#/monitor", "▶", "Live monitoring"], ["#/cases", "◆", "Safety Cases"],
  ["#/passport", "▤", "Safety Passport"], ["#/blackbox", "◷", "Black Box"], ["#/firepack", "✚", "Fire Pack"], ["#/evidence", "✓", "AI evidence"],
];

function App() {
  const hash = useHash();
  const [facility, setFacility] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [state, setState] = useState(null);
  const [ticks, setTicks] = useState([]);
  const [cases, setCases] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [role, setRole] = useState("operator");
  const [names] = useState({ technician: "Amine B. (technician)", verifier: "Sami K. (HSE verifier)" });
  const [msg, setMsg] = useState(null);
  const [online, setOnline] = useState(true);
  const tickRef = useRef({ event: null, ticks: [] });

  const toast = (text, err) => { setMsg({ text, err }); setTimeout(() => setMsg(null), 4500); };
  useEffect(() => { api("/api/facility").then(setFacility); api("/api/replay/catalog").then(setCatalog); }, []);

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
  usePoll(refresh, 800, []);
  usePoll(async () => { setCases(await api("/api/cases")); setAlerts(await api("/api/alerts")); }, 2000, []);

  const ctx = { facility, catalog, state, ticks, cases, alerts, refresh, toast, role, names };
  const open = cases.filter(c => c.status !== "CLOSED").length;
  const route = hash.replace(/^#/, "");
  let page, title, sub;
  if (route.startsWith("/cases/")) { const id = route.split("/")[2]; page = html`<${CaseDetail} id=${id} ctx=${ctx} key=${id}/>`; title = `Safety Case ${id}`; sub = "Evidence, response workflow and audit trail"; }
  else ({
    "/": () => { page = html`<${Overview} ctx=${ctx}/>`; title = "Operational overview"; sub = facility ? `${facility.name} · ${facility.site}` : ""; },
    "/monitor": () => { page = html`<${Monitor} ctx=${ctx}/>`; title = "Live monitoring"; sub = "Real recorded sensor data, replayed and analysed by the trained model"; },
    "/cases": () => { page = html`<${Cases} ctx=${ctx}/>`; title = "Digital Safety Cases"; sub = "Closed only with technician, independent verifier and measured stabilization"; },
    "/passport": () => { page = html`<${Passport} ctx=${ctx}/>`; title = "Digital Safety Passport"; sub = "History and integrity of the monitored zone"; },
    "/blackbox": () => { page = html`<${BlackBox} ctx=${ctx}/>`; title = "Black Box"; sub = "Chronological record of everything that happened"; },
    "/firepack": () => { page = html`<${FirePack} ctx=${ctx}/>`; title = "Emergency Fire Pack"; sub = "For the Protection Civile"; },
    "/evidence": () => { page = html`<${Evidence} ctx=${ctx}/>`; title = "AI evidence"; sub = "What the real data supports, and what it does not"; },
  }[route] || (() => { page = html`<div class="page"><div class="empty">Page not found. <a href="#/">Back to overview</a></div></div>`; title = "Not found"; }))();

  return html`<div class="shell">
    <aside class="side">
      <div class="brand"><svg viewBox="0 0 32 32"><path d="M16 2 4 7v8c0 7.5 5.1 13.6 12 15 6.9-1.4 12-7.5 12-15V7z" fill="#f59e0b"/><path d="M11 17l4 4 7-9" stroke="#1a1205" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div><b>AEROGUARD</b><span>TRUST · CONTROL ROOM</span></div></div>
      <nav class="nav">${NAV.map(([h, i, t]) => html`<a href=${h} class=${(h === "#/" ? hash === "#/" || hash === "" : hash.startsWith(h)) ? "on" : ""}>
        <span class="ico">${i}</span>${t}${t === "Safety Cases" && open ? html`<span class="badge">${open}</span>` : ""}</a>`)}</nav>
      <div class="foot">Prototype · historical replay of real recordings (Industrial Hall dataset, CC BY 4.0) · demo roles · Hedera pending
        <div style="margin-top:8px"><button class="btn sm ghost" onClick=${async () => { if (confirm("Clear all demo cases and events?")) { await api("/api/demo/reset", {}); location.hash = "#/monitor"; refresh(); } }}>Reset demo</button></div></div>
    </aside>
    <main class="main">
      <div class="top"><div><h1>${title}</h1><div class="sub">${sub}</div></div><span class="grow"></span>
        ${!online && html`<span class="pill bad">backend offline</span>`}
        <label class="role"><small>Demo role</small><select value=${role} onChange=${e => setRole(e.target.value)}>
          <option value="operator">Control-room operator</option><option value="technician">${names.technician}</option><option value="verifier">${names.verifier}</option></select></label>
      </div>
      ${page}
    </main>
    ${msg && html`<div class=${`toast ${msg.err ? "err" : ""}`}>${msg.text}</div>`}
  </div>`;
}

render(html`<${App}/>`, document.getElementById("app"));
