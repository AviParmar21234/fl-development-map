/* Morgan Group · Florida Development Radar — map */
(() => {
  const TYPE_META = {
    "rezoning": ["Rezoning", "#d4593c"],
    "land-use": ["Land Use", "#2a8f83"],
    "site-plan": ["Site Plan", "#3b6fb3"],
    "pud": ["PUD", "#7a5cad"],
    "plat": ["Plat", "#4d9455"],
    "variance": ["Variance", "#8a8f96"],
    "special-exception": ["Special Exception", "#c78f2c"],
    "development-agreement": ["Dev Agreement", "#b8547e"],
    "annexation": ["Annexation", "#7d8a3d"],
    "other-development": ["Other", "#6d7278"],
  };
  const typeLabel = (t) => (TYPE_META[t] || ["Development"])[0];
  const typeColor = (t) => (TYPE_META[t] || [null, "#6d7278"])[1];

  const REGIONS = {
    south: { name: "South Florida", counties: ["Miami-Dade", "Broward", "Palm Beach"] },
    central: { name: "Central Florida", counties: ["Orange", "Osceola", "Seminole", "Lake", "Hillsborough", "Pinellas", "Polk"] },
  };
  const params = new URLSearchParams(location.search);

  const map = L.map("map", { zoomControl: false }).setView([27.2, -81.6], 7);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd", maxZoom: 19,
  }).addTo(map);
  const pinLayer = L.layerGroup().addTo(map);

  const state = {
    q: "", mfOnly: false, newOnly: false, status: "all",
    counties: new Set(), types: new Set(Object.keys(TYPE_META)),
    features: [], unmapped: [], coverage: [],
    newCutoff: null,
    entities: {},          // key -> entity (all, unfiltered)
    markerByKey: {},       // key -> marker (currently rendered)
    entityByItemId: {},    // item id -> entity key
    selectedKey: null,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function computeNewCutoff(meta) {
    const dates = new Set(state.features.map((f) => f.properties.first_seen).filter(Boolean));
    if (dates.size <= 1) return null;
    const gen = meta ? meta.generated_at.slice(0, 10) : new Date().toISOString().slice(0, 10);
    const d = new Date(gen); d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  }
  const isNew = (p) => state.newCutoff && p.first_seen && p.first_seen >= state.newCutoff;

  /* ---------- property entities: one site = one pin, never grouped ---------- */
  function buildEntities() {
    state.entities = {};
    state.entityByItemId = {};
    for (const f of state.features) {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
      let e = state.entities[key];
      if (!e) {
        e = state.entities[key] = { key, lat, lon, items: [] };
      }
      e.items.push(p);
      state.entityByItemId[p.id] = key;
    }
    for (const e of Object.values(state.entities)) {
      e.items.sort((a, b) => (b.meeting_date || "").localeCompare(a.meeting_date || ""));
      e.address = (e.items.find((i) => i.address) || {}).address || null;
      e.parcel = (e.items.find((i) => i.parcel) || {}).parcel || null;
      e.jurisdiction = e.items[0].jurisdiction;
      e.county = e.items[0].county;
      e.best = [...e.items].sort((a, b) => (b.score || 0) - (a.score || 0))[0];
    }
  }

  function matches(p) {
    if (state.mfOnly && !p.multifamily) return false;
    if (state.newOnly && !isNew(p)) return false;
    if (state.status !== "all" && p.status !== state.status) return false;
    if (state.counties.size && !state.counties.has(p.county)) return false;
    if (!state.types.has(p.project_type)) return false;
    if (state.q) {
      const hay = `${p.title} ${p.plain || ""} ${p.address || ""} ${p.jurisdiction} ${p.meeting_body}`.toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    return true;
  }
  const visibleItems = (e) => e.items.filter(matches);

  /* ---------- pins ---------- */
  function pinIcon(e, active) {
    const vis = visibleItems(e);
    const mf = vis.some((i) => i.multifamily);
    const fresh = vis.some((i) => isNew(i));
    const best = [...vis].sort((a, b) => (b.score || 0) - (a.score || 0))[0] || e.best;
    const color = typeColor(best && best.project_type);
    const w = mf ? 30 : 24, h = mf ? 40 : 32;
    // fill = project type color; multifamily/selected pins get a charcoal outline and white core
    const stroke = active ? "#1a1c1f" : (mf ? "#26282c" : "#ffffff");
    return L.divIcon({
      className: "pin-wrap" + (active ? " pin-active" : ""),
      html: `<svg width="${w}" height="${h}" viewBox="0 0 30 40">
        <path d="M15 1 C7 1 1.5 7 1.5 14.5 C1.5 24 15 39 15 39 C15 39 28.5 24 28.5 14.5 C28.5 7 23 1 15 1 Z"
              fill="${color}" stroke="${stroke}" stroke-width="${active ? 2.6 : (mf ? 2.2 : 1.6)}"/>
        <circle cx="15" cy="14.5" r="5" fill="#ffffff"/>
        ${fresh ? '<circle cx="25" cy="6" r="4.4" fill="#3e9e5c" stroke="#fff" stroke-width="1.4"/>' : ""}
      </svg>`,
      iconSize: [w, h],
      iconAnchor: [w / 2, h],
      tooltipAnchor: [0, -h + 6],
    });
  }

  function render() {
    pinLayer.clearLayers();
    state.markerByKey = {};
    let sites = 0, mf = 0, upcoming = 0;
    for (const e of Object.values(state.entities)) {
      const vis = visibleItems(e);
      if (!vis.length) continue;
      sites++;
      if (vis.some((i) => i.multifamily)) mf++;
      if (vis.some((i) => i.status === "upcoming")) upcoming++;
      const m = L.marker([e.lat, e.lon], {
        icon: pinIcon(e, e.key === state.selectedKey),
        riseOnHover: true,
      });
      m.bindTooltip(esc(e.address || e.parcel || e.jurisdiction), { direction: "top", opacity: 0.95 });
      m.on("click", () => selectEntity(e.key, false));
      m.addTo(pinLayer);
      state.markerByKey[e.key] = m;
    }
    $("statMapped").textContent = sites;
    $("statMF").textContent = mf;
    $("statUpcoming").textContent = upcoming;
    if (state.selectedKey && !state.markerByKey[state.selectedKey]) closeCard();
    if (openDrawer === "hearings" || openDrawer === "projects") renderDrawer();
  }

  /* ---------- property card (its own entity, news-style) ---------- */
  function cardHTML(e) {
    const vis = visibleItems(e);
    const mf = vis.some((i) => i.multifamily);
    const units = Math.max(0, ...vis.map((i) => i.units || 0));
    const acres = Math.max(0, ...vis.map((i) => i.acres || 0));
    const score = Math.max(0, ...vis.map((i) => i.score || 0));
    const facts = [
      units ? `${units} units` : "",
      acres ? `${acres} ac` : "",
      score ? `★ ${score}/8` : "",
    ].filter(Boolean).join(" · ");
    const rows = vis.map((i) => `
      <div class="pc-item">
        <div class="pc-item-head">
          <span class="pc-type"><i class="pc-type-dot" style="background:${typeColor(i.project_type)}"></i>${typeLabel(i.project_type)}</span>
          ${i.multifamily ? '<span class="pc-type pc-type-mf">Multifamily</span>' : ""}
          ${isNew(i) ? '<span class="pc-type pc-type-new">New</span>' : ""}
          <span class="pc-date">${esc(i.meeting_date || "")}${i.status === "upcoming" ? " · upcoming" : ""}</span>
        </div>
        <p class="pc-plain">${esc(i.plain || i.title)}</p>
        <p class="pc-legal">${esc(i.title.slice(0, 170))}${i.title.length > 170 ? "…" : ""}</p>
        <div class="pc-meta">${esc(i.meeting_body)} · <a href="${esc(i.link)}" target="_blank" rel="noopener">View source →</a></div>
      </div>`).join("");
    return `
      <p class="pc-kicker">${mf ? "Multifamily site" : "Development site"} · ${esc(e.county)} County</p>
      <h2 class="pc-title">${esc(e.address || (e.parcel ? "Parcel " + e.parcel : e.jurisdiction))}</h2>
      <p class="pc-sub">${esc(e.jurisdiction)}${facts ? ` · ${facts}` : ""}</p>
      <div class="pc-items">${rows}</div>`;
  }

  function selectEntity(key, fly) {
    const prev = state.selectedKey;
    state.selectedKey = key;
    const e = state.entities[key];
    if (prev && state.markerByKey[prev]) state.markerByKey[prev].setIcon(pinIcon(state.entities[prev], false));
    if (state.markerByKey[key]) state.markerByKey[key].setIcon(pinIcon(e, true));
    $("pcBody").innerHTML = cardHTML(e);
    $("propCard").hidden = false;
    if (fly) map.setView([e.lat, e.lon], Math.max(map.getZoom(), 15), { animate: true });
  }
  function closeCard() {
    if (state.selectedKey && state.markerByKey[state.selectedKey]) {
      state.markerByKey[state.selectedKey].setIcon(pinIcon(state.entities[state.selectedKey], false));
    }
    state.selectedKey = null;
    $("propCard").hidden = true;
  }
  $("pcClose").onclick = closeCard;
  map.on("click", closeCard);

  /* ---------- filters UI ---------- */
  function buildCountyChips() {
    const counts = {};
    for (const f of state.features) counts[f.properties.county] = (counts[f.properties.county] || 0) + 1;
    const el = $("countyChips");
    el.innerHTML = "";
    Object.keys(counts).sort().forEach((c) => {
      const b = document.createElement("button");
      b.className = "chip" + (state.counties.has(c) ? " on" : "");
      b.textContent = c;
      b.onclick = () => {
        state.counties.has(c) ? state.counties.delete(c) : state.counties.add(c);
        b.classList.toggle("on");
        render();
      };
      el.appendChild(b);
    });
  }

  function buildTypeChecks() {
    const el = $("typeChecks");
    el.innerHTML = "";
    for (const [key, [label, color]] of Object.entries(TYPE_META)) {
      const lab = document.createElement("label");
      lab.className = "type-check on";
      lab.innerHTML = `<input type="checkbox" checked><span class="type-dot" style="--tc:${color}"></span>${label}`;
      lab.querySelector("input").onchange = (ev) => {
        ev.target.checked ? state.types.add(key) : state.types.delete(key);
        lab.classList.toggle("on", ev.target.checked);
        render();
      };
      el.appendChild(lab);
    }
  }

  /* ---------- drawers ---------- */
  let openDrawer = null;
  function drawerRow(p, i) {
    const key = state.entityByItemId[p.id];
    return `
      <div class="u-item p-item" data-key="${key || ""}">
        ${i != null ? `<span class="p-rank">${i + 1}</span>` : ""}<a href="${esc(p.link)}" target="_blank" rel="noopener">${esc((p.plain || p.title).slice(0, 110))}</a>
        <div class="u-meta">${esc(p.jurisdiction)}${p.meeting_date ? ` · ${esc(p.meeting_date)}` : ""} · ★ ${p.score || 0}${isNew(p) ? ' · <b class="u-new">new</b>' : ""}</div>
      </div>`;
  }
  function wireRows(d) {
    d.querySelectorAll(".p-item").forEach((el) => {
      el.addEventListener("click", (ev) => {
        if (ev.target.tagName === "A") return;
        if (el.dataset.key) selectEntity(el.dataset.key, true);
      });
    });
  }
  function renderDrawer() {
    const d = $("drawer");
    if (!openDrawer) { d.hidden = true; return; }
    d.hidden = false;
    if (openDrawer === "projects") {
      const seen = new Set();
      const ranked = state.features.map((f) => f.properties)
        .filter((p) => matches(p))
        .sort((a, b) => (b.score || 0) - (a.score || 0) || (b.meeting_date || "").localeCompare(a.meeting_date || ""))
        .filter((p) => {
          const k = state.entityByItemId[p.id];
          if (seen.has(k)) return false;
          seen.add(k);
          return true;
        })
        .slice(0, 60);
      d.innerHTML = ranked.length ? ranked.map((p, i) => drawerRow(p, i)).join("")
        : '<div class="u-meta" style="padding:12px 0">No sites match the current filters.</div>';
      wireRows(d);
    } else if (openDrawer === "hearings") {
      const today = new Date().toISOString().slice(0, 10);
      const horizon = new Date(); horizon.setDate(horizon.getDate() + 14);
      const hz = horizon.toISOString().slice(0, 10);
      const up = state.features.map((f) => f.properties)
        .filter((p) => matches(p) && p.meeting_date >= today && p.meeting_date <= hz)
        .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date) || (b.score || 0) - (a.score || 0));
      d.innerHTML = up.length ? up.map((p) => `
        <div class="u-item p-item" data-key="${state.entityByItemId[p.id] || ""}">
          <div class="h-date">${esc(p.meeting_date)}</div>
          <a href="${esc(p.link)}" target="_blank" rel="noopener">${esc((p.plain || p.title).slice(0, 110))}</a>
          <div class="u-meta">${esc(p.jurisdiction)} · ${esc(p.meeting_body)}</div>
        </div>`).join("")
        : '<div class="u-meta" style="padding:12px 0">No hearings in the next 14 days match the current filters.</div>';
      wireRows(d);
    } else if (openDrawer === "unmapped") {
      d.innerHTML = state.unmapped.length
        ? state.unmapped.map((u) => `
          <div class="u-item">
            <a href="${esc(u.link)}" target="_blank" rel="noopener">${esc((u.plain || u.title).slice(0, 130))}</a>
            <div class="u-meta">${esc(u.jurisdiction)} · ${esc(u.meeting_date || "no date")} · no mappable address</div>
          </div>`).join("")
        : '<div class="u-meta" style="padding:12px 0">Every development item has a mapped location.</div>';
    } else {
      d.innerHTML = state.coverage.map((c) => `
        <div class="cov-row">
          <b>${esc(c.name)}</b>
          <span>${c.ok ? `<span class="cov-ok">${c.items_dev} dev / ${c.items_raw} raw</span>` : `<span class="cov-err" title="${esc(c.error || "")}">failed</span>`}</span>
        </div>`).join("");
    }
  }
  document.querySelectorAll(".drawer-tabs button").forEach((btn) => {
    btn.onclick = () => {
      openDrawer = openDrawer === btn.dataset.drawer ? null : btn.dataset.drawer;
      document.querySelectorAll(".drawer-tabs button").forEach((b) =>
        b.classList.toggle("active", b.dataset.drawer === openDrawer));
      renderDrawer();
    };
  });

  /* ---------- panel + inputs ---------- */
  $("collapseBtn").onclick = () => {
    const hidden = document.body.classList.toggle("panel-hidden");
    $("collapseBtn").textContent = hidden ? "›" : "‹";
    setTimeout(() => map.invalidateSize(), 300);
  };
  $("search").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
  $("mfOnly").addEventListener("change", (e) => { state.mfOnly = e.target.checked; render(); });
  $("newOnly").addEventListener("change", (e) => { state.newOnly = e.target.checked; render(); });
  $("statusSel").addEventListener("change", (e) => { state.status = e.target.value; render(); });

  function exportCSV() {
    const cols = ["id","score","multifamily","units","acres","project_type","status","meeting_date",
                  "jurisdiction","county","meeting_body","address","parcel","plain","title","link","first_seen"];
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""').replace(/\s+/g, " ")}"`;
    const rows = [cols.join(",")];
    const all = [...state.features.map((f) => f.properties), ...state.unmapped];
    for (const p of all) {
      if (!matches(p)) continue;
      rows.push(cols.map((c) => q(p[c])).join(","));
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `morgan-fl-projects-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  $("csvBtn").addEventListener("click", exportCSV);

  /* ---------- load ---------- */
  Promise.all([
    fetch("data/projects.geojson").then((r) => r.json()),
    fetch("data/unmapped.json").then((r) => r.json()).catch(() => []),
    fetch("data/coverage.json").then((r) => r.json()).catch(() => []),
    fetch("data/meta.json").then((r) => r.json()).catch(() => null),
  ]).then(([fc, unmapped, coverage, meta]) => {
    state.features = fc.features || [];
    state.unmapped = unmapped;
    state.coverage = coverage;
    state.newCutoff = computeNewCutoff(meta);
    const wantCounty = params.get("county");
    const wantRegion = params.get("region");
    if (wantCounty) {
      wantCounty.split(",").forEach((c) => state.counties.add(c));
      $("brandSub").textContent = wantCounty.replace(",", " · ") + " County";
    } else if (wantRegion && REGIONS[wantRegion]) {
      REGIONS[wantRegion].counties.forEach((c) => state.counties.add(c));
      $("brandSub").textContent = REGIONS[wantRegion].name;
    }
    buildEntities();
    buildCountyChips();
    buildTypeChecks();
    render();
    const today = new Date().toISOString().slice(0, 10);
    const nHear = state.features.filter((f) => f.properties.meeting_date >= today).length;
    $("hearingsCount").textContent = nHear ? `(${nHear})` : "";
    $("unmappedCount").textContent = unmapped.length ? `(${unmapped.length})` : "";
    $("coverageCount").textContent = coverage.length ? `(${coverage.length})` : "";
    $("statSources").textContent = coverage.filter((c) => c.ok).length || "–";
    if (meta) $("updatedAt").textContent = `Updated ${meta.generated_at.slice(0, 16).replace("T", " ")} UTC · public-record sources`;
    const visible = Object.values(state.entities).filter((e) => visibleItems(e).length);
    if (visible.length) {
      const b = L.latLngBounds(visible.map((e) => [e.lat, e.lon]));
      if (b.isValid()) map.fitBounds(b.pad(0.08));
    }
    openDrawer = "projects";
    document.querySelectorAll(".drawer-tabs button").forEach((b) =>
      b.classList.toggle("active", b.dataset.drawer === "projects"));
    renderDrawer();
  }).catch((err) => {
    $("updatedAt").textContent = "Data failed to load — run ./refresh.sh";
    console.error(err);
  });
})();
