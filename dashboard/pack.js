/* ARGOS firefighter briefing page. Vanilla JS, no build step. All text is escaped before rendering. */
(function () {
  "use strict";
  const root = document.getElementById("pack");
  const caseId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  const qs = new URLSearchParams(location.search);
  const token = qs.get("t") || "";
  const fromConsole = qs.get("src") === "console";      // opened from the ARGOS control room on this machine
  const api = `/api/pack/${encodeURIComponent(caseId)}?t=${encodeURIComponent(token)}`;
  const pdf = `/api/pack/${encodeURIComponent(caseId)}/briefing.pdf?t=${encodeURIComponent(token)}`;
  let data = null, lastOk = null, offline = false, zoom = false;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (ts) => { if (!ts) return "—"; const d = new Date(ts); return isNaN(d) ? esc(ts) : d.toLocaleString([], { dateStyle: "medium", timeStyle: "medium" }); };
  const fmtRec = (ts) => (ts ? esc(String(ts).replace("T", " ").replace("+00:00", "").slice(0, 19)) + " (recorded time)" : "—");
  const clock = (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const pct = (p) => (p == null ? "—" : Math.round(p * 100) + " %");
  const arrow = { rising: "▲ rising", falling: "▼ falling", stable: "▬ stable", unknown: "" };

  // ------------------------------------------------------------------ floor plan (SVG, 1 m = 20 units)
  const S = 20;
  const ROOM = { production: "#FFFFFF", electrical: "#FBF0DC", corridor: "#EFEBE4", plant: "#F4F1EC", office: "#F4F1EC", storage: "#F4F1EC",
    hazard: "#FBE7E5", workshop: "#F4F1EC", outdoor: "#FAF8F4", equipment: "#E2DDD5" };
  function plan(m) {
    const s = m.site, W = s.size_m.width, H = s.size_m.height, o = [];
    o.push(`<defs><pattern id="hz" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="#FBE7E5"/><line x1="0" y1="0" x2="0" y2="8" stroke="#E7A49D" stroke-width="3"/></pattern>
      <radialGradient id="fireg"><stop offset="0" stop-color="#B3261E" stop-opacity=".42"/><stop offset="1" stop-color="#B3261E" stop-opacity=".1"/></radialGradient></defs>`);
    o.push(`<rect x="0" y="0" width="${W * S}" height="${H * S}" fill="none" stroke="#C7C4BF" stroke-dasharray="8 6"/>`);
    for (const r of s.rooms) {
      const out = r.type === "outdoor";
      o.push(`<rect x="${r.x * S}" y="${r.y * S}" width="${r.w * S}" height="${r.h * S}" fill="${r.type === "hazard" ? "url(#hz)" : ROOM[r.type] || "#fff"}"
        stroke="${out ? "#C7C4BF" : "#292A29"}" stroke-width="${r.id === "HALL-A" ? 3 : 1.6}" ${out ? 'stroke-dasharray="6 4"' : ""}/>`);
      const ty = (r.label_above ? r.y - 0.7 : r.y + r.h / 2) * S, fs = r.w < 9 ? 13 : 17;
      const words = r.label.split(" "), fits = r.label.length * fs * 0.56 <= r.w * S - 10;
      const lines = fits ? [r.label] : [words.slice(0, Math.ceil(words.length / 2)).join(" "), words.slice(Math.ceil(words.length / 2)).join(" ")];
      lines.forEach((ln, i) => o.push(`<text x="${(r.x + r.w / 2) * S}" y="${ty + (i - (lines.length - 1) / 2) * fs * 1.1}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="#292A29">${esc(ln)}</text>`));
      if (r.sub && (r.h >= 5 || r.label_above)) o.push(`<text x="${(r.x + r.w / 2) * S}" y="${r.label_above ? ty - fs - 2 : ty + lines.length * fs * 0.55 + 12}" text-anchor="middle" font-size="12.5" fill="#6B6158">${esc(r.sub)}</text>`);
    }
    for (const f of s.hall_features)
      o.push(`<rect x="${f.x * S}" y="${f.y * S}" width="${f.w * S}" height="${f.h * S}" fill="${f.type === "hazard" ? "url(#hz)" : ROOM[f.type] || "#eee"}" stroke="#88715F" stroke-width="1"><title>${esc(f.label)}</title></rect>`);
    for (const f of s.hall_features.filter((f) => f.type === "hazard"))
      o.push(`<text x="${(f.x + f.w / 2) * S}" y="${(f.y + 0.9) * S}" text-anchor="middle" font-size="10" fill="#9A5B00" font-weight="700">${esc(f.label)}</text>`);
    for (const h of s.hazards) {
      if (h.w) o.push(`<rect x="${(h.x - h.w / 2) * S}" y="${(h.y - h.h / 2) * S}" width="${h.w * S}" height="${h.h * S}" fill="url(#hz)" stroke="#B3261E"/>`);
      o.push(`<g><title>${esc(h.label)}: ${esc(h.detail)}</title><path d="M${h.x * S} ${(h.y - 1.05) * S} L${(h.x - 1.05) * S} ${(h.y + 0.8) * S} L${(h.x + 1.05) * S} ${(h.y + 0.8) * S} Z" fill="#E8A317" stroke="#292A29" stroke-width="1.2"/>
        <text x="${h.x * S}" y="${(h.y + 0.55) * S}" text-anchor="middle" font-size="15" font-weight="900" fill="#292A29">!</text></g>`);
    }
    if (m.incident) {
      const i = m.incident;
      o.push(`<circle cx="${i.x * S}" cy="${i.y * S}" r="${i.r * S}" fill="url(#fireg)" stroke="#B3261E" stroke-width="2.5" stroke-dasharray="7 5"><animate attributeName="stroke-opacity" values="1;.35;1" dur="1.6s" repeatCount="indefinite"/></circle>`);
      o.push(`<rect x="${i.x * S - 112}" y="${(i.y - i.r) * S - 26}" width="224" height="22" rx="11" fill="#B3261E"/><text x="${i.x * S}" y="${(i.y - i.r) * S - 10.5}" text-anchor="middle" font-size="12" font-weight="800" fill="#fff">⚠ SUSPECTED INCIDENT AREA</text>`);
    }
    for (const n of m.sensors)
      o.push(`<circle cx="${n.x * S}" cy="${n.y * S}" r="${n.fire ? 9 : 6}" fill="${n.fire ? "#B3261E" : "#88715F"}" stroke="#fff" stroke-width="2"/><text x="${n.x * S + 12}" y="${n.y * S + 5}" font-size="${n.fire ? 15 : 11}" font-weight="${n.fire ? 800 : 400}" fill="${n.fire ? "#B3261E" : "#6B6158"}">${esc(n.label)}</text>`);
    for (const e of s.exits) {
      const v = e.side === "v", w = v ? 14 : 40, h = v ? 40 : 14;
      o.push(`<g><title>${esc(e.label)}</title><rect x="${e.x * S - w / 2}" y="${e.y * S - h / 2}" width="${w}" height="${h}" rx="3" fill="#2E7D4F" stroke="#fff" stroke-width="1.5"/></g>`);
    }
    for (const a of s.firefighter_access)
      o.push(`<g><title>${esc(a.label)}</title><rect x="${a.x * S - 26}" y="${a.y * S - 15}" width="52" height="30" rx="7" fill="#B3261E" stroke="#fff" stroke-width="2"/><text x="${a.x * S}" y="${a.y * S + 5}" text-anchor="middle" font-size="13" font-weight="800" fill="#fff">${esc(a.id)}</text></g>`);
    for (const p of s.power_isolation)
      o.push(`<g><title>${esc(p.label)}</title><rect x="${p.x * S - 13}" y="${p.y * S - 13}" width="26" height="26" rx="4" fill="#F2C230" stroke="#292A29" stroke-width="1.5"/><text x="${p.x * S}" y="${p.y * S + 5}" text-anchor="middle" font-size="14" font-weight="900" fill="#292A29">⚡</text></g>`);
    for (const x of s.extinguishers) o.push(`<g><title>${esc(x.label)}</title><circle cx="${x.x * S}" cy="${x.y * S}" r="8" fill="#D93A2B" stroke="#fff" stroke-width="2"/></g>`);
    for (const x of s.hydrants) o.push(`<g><title>${esc(x.label)}</title><path d="M${x.x * S} ${x.y * S - 14} l14 14 l-14 14 l-14 -14 Z" fill="#2F5F98" stroke="#fff" stroke-width="2"/><text x="${x.x * S}" y="${x.y * S + 4}" text-anchor="middle" font-size="11" font-weight="800" fill="#fff">H</text></g>`);
    for (const a of s.assembly_points) o.push(`<g><title>${esc(a.label)}</title><circle cx="${a.x * S}" cy="${a.y * S}" r="17" fill="#E6F2EA" stroke="#2E7D4F" stroke-width="3"/><text x="${a.x * S}" y="${a.y * S + 4.5}" text-anchor="middle" font-size="12" font-weight="800" fill="#2E7D4F">AP</text></g>`);
    for (const b of m.blocked || [])
      o.push(`<g><title>${esc(b.label)}</title><circle cx="${b.x * S}" cy="${b.y * S}" r="15" fill="#fff" stroke="#111" stroke-width="2"/><path d="M${b.x * S - 9} ${b.y * S - 9} l18 18 M${b.x * S + 9} ${b.y * S - 9} l-18 18" stroke="#111" stroke-width="4"/></g>`);
    o.push(`<g transform="translate(${(W - 1) * S} ${0.8 * S})"><path d="M0 0 l-8 22 l8 -6 l8 6 Z" fill="#292A29"/><text y="36" text-anchor="middle" font-size="12" font-weight="800">N</text></g>`);
    o.push(`<text x="4" y="${H * S + 26}" font-size="13" font-weight="800" fill="#B3261E">DEMONSTRATION LAYOUT · FICTIONAL FACTORY · NOT A REAL FACILITY</text>`);
    return `<svg viewBox="${-1.5 * S} ${-1.5 * S} ${(W + 3) * S} ${(H + 4) * S}" role="img" aria-label="Floor plan of the fictional demonstration factory with the suspected incident area, exits, firefighter access points, power isolation, extinguishers, hydrants, hazards and assembly points">${o.join("")}</svg>`;
  }
  const LEG = [
    ['<circle cx="11" cy="11" r="9" fill="#B3261E" fill-opacity=".25" stroke="#B3261E" stroke-dasharray="3 2"/>', "Suspected incident area"],
    ['<circle cx="11" cy="11" r="6" fill="#B3261E"/>', "Sensor with fire signal"],
    ['<rect x="7" y="2" width="8" height="18" rx="2" fill="#2E7D4F"/>', "Emergency exit"],
    ['<rect x="1" y="4" width="20" height="14" rx="3" fill="#B3261E"/>', "Firefighter access"],
    ['<rect x="3" y="3" width="16" height="16" rx="3" fill="#F2C230" stroke="#292A29"/>', "Power isolation"],
    ['<circle cx="11" cy="11" r="6" fill="#D93A2B"/>', "Extinguisher"],
    ['<path d="M11 1 l10 10 l-10 10 l-10 -10 Z" fill="#2F5F98"/>', "Hydrant"],
    ['<path d="M11 2 L20 19 L2 19 Z" fill="#E8A317" stroke="#292A29"/>', "Known hazard"],
    ['<circle cx="11" cy="11" r="8" fill="#E6F2EA" stroke="#2E7D4F" stroke-width="2.5"/>', "Assembly point"],
    ['<path d="M4 4 l14 14 M18 4 l-14 14" stroke="#111" stroke-width="3.5"/>', "Blocked passage (reported)"],
  ].map(([g, t]) => `<span><svg width="22" height="22" viewBox="0 0 22 22">${g}</svg>${esc(t)}</span>`).join("");

  // ------------------------------------------------------------------ sections
  function render() {
    const b = data, inc = b.incident, loc = inc.location, acc = b.access, ai = b.ai_assessment, v = b.verification;
    const near = acc.hazards.filter((h) => h.near_incident);
    const fireLabels = b.sensor_observations.filter((o) => o.fire_signal).map((o) => o.label);
    const hv = v.hedera;
    const hTag = !hv ? "" : hv.status === "VERIFIED" ? '<span class="tag t-ok">✓ verified on Hedera</span>'
      : hv.status === "NOT_ANCHORED" ? '<span class="tag t-unk">not anchored</span>' : hv.status === "MISMATCH" ? '<span class="tag t-bad">⚠ mismatch</span>'
      : `<span class="tag t-wait">${esc(hv.status.replaceAll("_", " ").toLowerCase())}</span>`;

    root.innerHTML = `
    ${backBar()}
    <header class="sev ${esc(inc.severity)}" role="banner">
      <div class="l1"><span class="ic">⚠</span>${esc(inc.severity_text.toUpperCase())} · FIRE SIGNAL</div>
      <div class="l2">Incident <b>${esc(inc.id)}</b> · ${esc(inc.site_name)} · ${esc(inc.zone_name)}</div>
      <div class="upd"><span class="dot ${offline ? "off" : ""}"></span>${offline ? `Connection lost · showing data from ${clock(lastOk)}` : `Live · updated ${clock(lastOk)}`}
        · status: ${esc(inc.status_text)}</div>
    </header>
    <div class="demo"><b>DEMO ACCESS</b> · fictional factory data · decision support, <b>not an approved emergency response plan</b></div>
    <main class="wrap">
      ${offline ? `<div class="offline" role="alert">⚠ The ARGOS server cannot be reached. This page needs network access to update. Use the printed or downloaded PDF briefing as backup.</div>` : ""}
      <section class="summary" aria-label="Immediate summary">
        <div class="row"><div class="k">Where</div><div class="v big">${loc ? esc(loc.text) : "Location unknown"}</div></div>
        <div class="row"><div class="k">What</div><div class="v">Fire signal measured by ${fireLabels.length} sensor(s)${fireLabels.length ? " (" + esc(fireLabels.join(", ")) + ")" : ""} · AI fire likelihood up to ${pct(ai.max_p_fire_at_detection)}</div></div>
        <div class="row"><div class="k">Near hazards</div><div class="v">${near.length ? near.map((h) => `<span style="color:var(--crit)">${esc(h.label)}</span> (~${esc(h.distance_m)} m)`).join(" · ") : "None within 15 m on the layout"}</div></div>
        <div class="row"><div class="k">Detected</div><div class="v">${fmtRec(inc.detected_recorded_ts)}<div class="muted small">Incident opened ${fmt(inc.opened_wall_ts)}</div></div></div>
        <div class="row"><div class="k">Current</div><div class="v">${b.live.available ? `${esc(b.live.level_text)} <span class="muted small">at ${fmtRec(b.live.data_ts)}</span>` : '<span class="muted">No live readings for this incident right now</span>'}</div></div>
        <div class="row"><div class="k">Last update</div><div class="v">${fmt(inc.last_update_wall)}</div></div>
      </section>
      <nav class="chips" aria-label="Jump to section">
        <a href="#map">Map</a><a href="#access">Access &amp; hazards</a><a href="#know">What we know</a><a href="#sensors">Sensors</a><a href="#timeline">Timeline</a>
        <a class="pdf" href="${pdf}" download>⬇ PDF backup</a>
      </nav>

      <section class="card" id="map"><h2>Factory floor plan <span class="r tag t-demo">demonstration data</span></h2>
        <div class="mapbox ${zoom ? "zoom" : ""}">${plan(b.map)}</div>
        <div class="maptools"><button class="btn" id="zoom">${zoom ? "Fit to screen" : "Enlarge map"}</button><span class="muted small">Tap a symbol for its name. ${zoom ? "Swipe sideways to pan." : ""}</span></div>
        <div class="legend">${LEG}</div>
        ${loc ? `<div class="alert">⚠ ${esc(loc.text)}. <span style="font-weight:400">${esc(loc.basis)}</span></div>` : ""}
      </section>

      <section class="card" id="access"><h2>Emergency access &amp; hazards <span class="r tag t-demo">demonstration data</span></h2>
        <div class="warn">${esc(acc.route_note)}</div>
        <div class="grid2">
          <div><h3 class="small muted">FIREFIGHTER ACCESS POINTS</h3><ul class="list">${acc.firefighter_access.map((a) => `<li><span class="ico fb">${esc(a.id.replace("FA-", ""))}</span><div><b>${esc(a.label)}</b><div class="muted small">${esc(a.note)}</div></div></li>`).join("")}</ul></div>
          <div><h3 class="small muted">BLOCKED PASSAGES</h3><ul class="list">${acc.blocked.length ? acc.blocked.map((x) => `<li><span class="ico bl">✕</span><div><b>${esc(x.label)}</b><div class="muted small">${esc(x.source || "configured")}</div></div></li>`).join("") : '<li><span class="ico ex">✓</span><div>None known or reported in ARGOS.<div class="muted small">Not a guarantee that passages are clear.</div></div></li>'}</ul></div>
        </div>
        <h3 class="small muted">HAZARDS · nearest to the suspected area first</h3>
        <ul class="list">${acc.hazards.map((h) => `<li class="${h.near_incident ? "near" : ""}"><span class="ico hz">!</span><div><b>${esc(h.label)}</b> ${h.near_incident ? '<span class="near-tag">NEAR INCIDENT</span>' : ""}<div class="small">${esc(h.detail)}</div>${h.distance_m != null ? `<div class="muted small">about ${esc(h.distance_m)} m from the suspected area</div>` : ""}</div></li>`).join("")}</ul>
        <div class="grid2">
          <div><h3 class="small muted">ELECTRICAL ISOLATION</h3><ul class="list">${acc.power_isolation.map((p) => `<li><span class="ico pw">⚡</span><div><b>${esc(p.id)}</b> ${esc(p.label)}</div></li>`).join("")}</ul></div>
          <div><h3 class="small muted">EMERGENCY EXITS</h3><ul class="list">${acc.exits.map((e) => `<li><span class="ico ex">EX</span><div>${esc(e.label)}</div></li>`).join("")}</ul></div>
          <div><h3 class="small muted">FIREFIGHTING RESOURCES</h3><ul class="list">${acc.hydrants.map((h) => `<li><span class="ico hy"><span>H</span></span><div>${esc(h.label)}</div></li>`).join("")}
            <li><span class="ico fx"></span><div>${acc.extinguishers.length} extinguishers: ${esc([...new Set(acc.extinguishers.map((x) => x.label))].join(", "))}</div></li></ul></div>
          <div><h3 class="small muted">ASSEMBLY POINTS</h3><ul class="list">${acc.assembly_points.map((a) => `<li><span class="ico ap">AP</span><div>${esc(a.label)}</div></li>`).join("")}</ul></div>
        </div>
        <h3 class="small muted">SAFETY NOTES</h3><ul class="list">${acc.safety_notes.map((n) => `<li>• ${esc(n)}</li>`).join("")}</ul>
        <h3 class="small muted">EMERGENCY CONTACTS</h3><ul class="list">${acc.contacts.map((c) => `<li><div style="flex:1">${esc(c.name)}</div>${/^[0-9 +]+$/.test(c.phone) ? `<a class="tel" href="tel:${esc(c.phone.replace(/ /g, ""))}">${esc(c.phone)}</a>` : `<span class="muted">${esc(c.phone)}</span>`}</li>`).join("")}</ul>
      </section>

      <section class="card" id="know"><h2>What we know</h2>
        <div class="know">
          <div class="kb fact"><span class="tag t-fact">Confirmed fact</span><ul>${b.confirmed_facts.map((f) => `<li>${esc(f.text)} <span class="muted small">· ${esc(f.source)}</span></li>`).join("")}</ul></div>
          <div class="kb obs"><span class="tag t-obs">Sensor observation</span><ul>${b.sensor_observations.map((o) => `<li>${esc(o.label)}: CO ${esc(o.readings.find((r) => r.key === "co_ppm")?.at_detection ?? "—")} ppm, particles ${esc(o.readings.find((r) => r.key === "pm_total")?.at_detection ?? "—")} at detection</li>`).join("") || "<li>No readings attached.</li>"}</ul></div>
          <div class="kb hyp"><span class="tag t-hyp">AI hypothesis</span><ul>${b.hypotheses.map((h) => `<li>${esc(h.text)}<div class="muted small">${esc(h.basis)}</div></li>`).join("") || "<li>None.</li>"}</ul></div>
          <div class="kb unk"><span class="tag t-unk">Unknown</span><ul>${b.unknowns.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></div>
        </div>
      </section>

      <section class="card" id="sensors"><h2>Sensor and AI analysis <span class="r tag t-obs">real recorded data · replay</span></h2>
        ${b.sensor_observations.map((o) => `<div class="sensor ${o.fire_signal ? "fire" : ""}"><div class="h"><span>${esc(o.label)} ${o.fire_signal ? '<span class="tag t-bad">fire signal</span>' : ""}</span>
          <span>AI fire likelihood ${pct(o.p_fire_at_detection)} at detection${o.p_fire_now != null ? ` · ${pct(o.p_fire_now)} now` : ""}</span></div>
          <div class="readings">${o.readings.map((r) => `<div class="rd">${esc(r.label)}<b>${esc(r.at_detection ?? "—")} <small>${esc(r.unit)}</small></b>${r.now != null ? `<span>now ${esc(r.now)} <span class="tr-${esc(r.trend)}">${arrow[r.trend] || ""}</span></span>` : '<span class="muted">at detection</span>'}</div>`).join("")}</div></div>`).join("")}
        <h3 class="small muted" style="margin-top:14px">AI ASSESSMENT <span class="tag t-hyp">hypothesis</span></h3>
        <dl class="kv"><dt>Model</dt><dd class="hash">${esc(ai.model || "—")}</dd><dt>Level at detection</dt><dd>${esc(ai.level_at_detection)}</dd>
          <dt>Reasons</dt><dd>${ai.reasons.map(esc).join("<br>")}</dd>
          ${ai.p_fire_trend ? `<dt>Recent trend</dt><dd><span class="tr-${esc(ai.p_fire_trend.trend)}">${arrow[ai.p_fire_trend.trend]}</span> ${pct(ai.p_fire_trend.from)} → ${pct(ai.p_fire_trend.to)}</dd>` : ""}</dl>
        <h3 class="small muted" style="margin-top:12px">UNCERTAINTY</h3><ul class="list">${ai.uncertainty.map((u) => `<li class="small">• ${esc(u)}</li>`).join("")}</ul>
      </section>

      <div class="grid2">
        <section class="card"><h2>Actions taken</h2><ul class="list">${b.actions.length ? b.actions.map((a) => `<li><div><b>${esc(a.role)}</b> <span class="muted small">${fmt(a.ts)}</span><div>${esc(a.text)}</div></div></li>`).join("") : "<li class='muted'>No intervention recorded yet.</li>"}</ul></section>
        <section class="card"><h2>Drone inspection <span class="r tag t-sim">simulated</span></h2>
          <div class="muted small">${esc(b.drone.note)}</div>
          <ul class="list">${b.drone.missions.map((m) => `<li><div><b>${esc(m.id)}</b> · ${esc(m.status.replaceAll("_", " ").toLowerCase())}<div class="small muted">${m.checkpoints.map((c) => esc(c.label) + (c.result ? ` (${esc(c.result)})` : "")).join(", ")}</div></div></li>`).join("") || "<li class='muted'>No inspection linked.</li>"}
          ${b.drone.findings.map((f) => `<li><span class="tag t-sim">illustrative</span> ${esc(f.type)} at ${esc(f.checkpoint)} (${esc(f.severity)})</li>`).join("")}</ul></section>
      </div>

      <section class="card" id="timeline"><h2>Incident timeline</h2>
        <ul class="tl">${b.timeline.map((e) => `<li class="${/opened|escalat|alert/.test(e.kind) ? "crit" : ""}"><div class="ts">${fmt(e.ts)}${e.data_ts ? " · " + fmtRec(e.data_ts) : ""}</div><div>${esc(e.title)}</div></li>`).join("")}</ul></section>

      <section class="card"><h2>Data provenance &amp; verification</h2>
        <dl class="kv">
          <dt>Sensor data</dt><dd>Historical replay of a real recorded experiment (${esc(inc.replay_event)}), Industrial Hall dataset</dd>
          <dt>Facility layout</dt><dd><span class="tag t-demo">fictional demo</span> ${esc(b.demo_note)}</dd>
          <dt>Drone</dt><dd><span class="tag t-sim">simulated</span></dd>
          <dt>Local evidence</dt><dd>${v.local_chain_ok ? '<span class="tag t-ok">✓ intact</span>' : '<span class="tag t-bad">⚠ broken</span>'} ${esc(v.chain_events)} events, ${esc(v.incident_events)} for this incident</dd>
          <dt>Hedera</dt><dd>${hTag} ${hv && hv.anchored_through_event ? `<span class="small">fingerprint through event ${esc(hv.anchored_through_event)}${hv.covers_this_incident ? " (includes this incident)" : " (taken before this incident's latest event)"}</span>` : ""}
            ${hv && hv.explorer ? `<div><a href="${esc(hv.explorer)}" target="_blank" rel="noopener noreferrer">Topic on HashScan ↗</a></div>` : ""}</dd>
          <dt>Link expires</dt><dd>${fmt(b.link_expires_at)}</dd>
          <dt>Generated</dt><dd>${fmt(b.generated_at)}</dd>
        </dl>
        <div class="muted small" style="margin-top:8px">${esc(v.note)}</div>
      </section>
      <a class="btn primary big noprint" href="${pdf}" download>⬇ Download the briefing PDF (offline backup)</a>
      <div class="foot">${esc(b.not_a_plan)} ${esc(b.network_note)} ARGOS does not contact emergency services automatically.</div>
    </main>`;
    const z = document.getElementById("zoom");
    if (z) z.onclick = () => { zoom = !zoom; render(); document.getElementById("map").scrollIntoView(); };
  }

  function backBar() {
    if (!fromConsole) return "";
    return `<div class="console" role="navigation"><span>Control-room preview of the firefighter view</span>
      <a href="/#/cases/${encodeURIComponent(caseId)}" id="back">← Back to incident ${esc(caseId)}</a></div>`;
  }

  function fail(status, msg) {
    root.innerHTML = backBar() + `<div class="err" role="alert"><h1>${status === 410 ? "Link expired" : status === 401 || status === 403 ? "Access denied" : "Briefing unavailable"}</h1>
      <p>${esc(msg)}</p><p class="muted small">This briefing is only available through a valid, time-limited link from the ARGOS incident page. If the server is unreachable, use the printed PDF briefing.</p></div>`;
  }

  async function load() {
    try {
      const r = await fetch(api, { cache: "no-store" });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { if (!data) fail(r.status, j.detail || r.statusText); else { offline = true; render(); } if (r.status === 410 || r.status === 403) data && fail(r.status, j.detail); return; }
      data = j; lastOk = new Date(); offline = false; render();
    } catch (e) {
      if (!data) fail(0, "The ARGOS server cannot be reached. This page needs network access to the server. Use the PDF briefing as an offline backup.");
      else { offline = true; render(); }
    }
  }
  load();
  setInterval(() => { if (!document.hidden) load(); }, 10000);
})();
