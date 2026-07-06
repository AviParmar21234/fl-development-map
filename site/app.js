/* Morgan Group · Florida Development Radar */
(() => {
  const TYPE_META = {
    "rezoning": ["Rezoning", "--c-rezoning"],
    "land-use": ["Land Use", "--c-land-use"],
    "site-plan": ["Site Plan", "--c-site-plan"],
    "pud": ["PUD", "--c-pud"],
    "plat": ["Plat", "--c-plat"],
    "variance": ["Variance", "--c-variance"],
    "special-exception": ["Special Exception", "--c-special-exception"],
    "development-agreement": ["Dev Agreement", "--c-development-agreement"],
    "annexation": ["Annexation", "--c-annexation"],
    "other-development": ["Other", "--c-other-development"],
  };
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  const REGIONS = {
    south: { name: "South Florida", counties: ["Miami-Dade", "Broward", "Palm Beach"] },
    central: { name: "Central Florida", counties: ["Orange", "Osceola", "Seminole", "Lake", "Hillsborough", "Pinellas", "Polk"] },
  };
  const params = new URLSearchParams(location.search);

  const map = L.map("map", { zoomControl: false }).setView([27.2, -81.6], 7);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd", maxZoom: 19,
  }).addTo(map);

  const cluster = L.markerClusterGroup({
    maxClusterRadius: 46,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
  });
  map.addLayer(cluster);

  const state = {
    q: "", mfOnly: false, newOnly: false, status: "all",
    counties: new Set(), types: new Set(Object.keys(TYPE_META)),
    features: [], unmapped: [], coverage: [],
    newCutoff: null, // items with first_seen >= this are NEW
    markerById: {},
  };

  function computeNewCutoff(meta) {
    const dates = new Set(state.features.map((f) => f.properties.first_seen).filter(Boolean));
    if (dates.size <= 1) return null; // first build: nothing is meaningfully "new"
    const gen = meta ? meta.generated_at.slice(0, 10) : new Date().toISOString().slice(0, 10);
    const d = new Date(gen); d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  }
  const isNew = (p) => state.newCutoff && p.first_seen && p.first_seen >= state.newCutoff;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function popupHTML(p) {
    const [label, varName] = TYPE_META[p.project_type] || ["Development", "--c-other-development"];
    const chips = [
      isNew(p) ? '<span class="pp-chip pp-chip-new">New</span>' : "",
      `<span class="pp-chip" style="background:${css(varName)}">${label}</span>`,
      p.multifamily ? '<span class="pp-chip pp-chip-mf">Multifamily</span>' : "",
      `<span class="pp-chip" style="background:#3a4454;color:#e8e4da">${p.status === "upcoming" ? "Upcoming" : "Heard"}</span>`,
    ].join("");
    const intel = [
      p.units ? `<b>${p.units}</b> units` : "",
      p.acres ? `<b>${p.acres}</b> ac` : "",
      p.score >= 5 ? `<b class="pp-hot">★ ${p.score}/8</b>` : (p.score ? `★ ${p.score}/8` : ""),
    ].filter(Boolean).join(" · ");
    return `
      <div class="pp-chips">${chips}</div>
      <div class="pp-title">${esc(p.plain || p.title)}</div>
      ${p.plain ? `<div class="pp-summary">${esc(p.title.slice(0, 200))}${p.title.length > 200 ? "…" : ""}</div>` : ""}
      <div class="pp-meta">
        <b>${esc(p.jurisdiction)}</b> · ${esc(p.county)} County<br>
        ${esc(p.meeting_body)}${p.meeting_date ? ` · <b>${esc(p.meeting_date)}</b>` : ""}<br>
        ${p.address ? esc(p.address) : (p.parcel ? "Parcel " + esc(p.parcel) : "")}
        ${intel ? `<br>${intel}` : ""}
      </div>
      <a class="pp-link" href="${esc(p.link)}" target="_blank" rel="noopener">View source item →</a>`;
  }

  function makeMarker(f) {
    const p = f.properties;
    const [, varName] = TYPE_META[p.project_type] || [null, "--c-other-development"];
    const size = p.multifamily ? 15 : 11;
    const icon = L.divIcon({
      className: "",
      html: `<div class="pin ${p.multifamily ? "pin-mf" : ""}" style="width:${size}px;height:${size}px;background:${css(varName)}"></div>`,
      iconSize: [size, size],
    });
    const [lon, lat] = f.geometry.coordinates;
    return L.marker([lat, lon], { icon }).bindPopup(popupHTML(p));
  }

  function matches(p) {
    if (state.mfOnly && !p.multifamily) return false;
    if (state.newOnly && !isNew(p)) return false;
    if (state.status !== "all" && p.status !== state.status) return false;
    if (state.counties.size && !state.counties.has(p.county)) return false;
    if (!state.types.has(p.project_type)) return false;
    if (state.q) {
      const hay = `${p.title} ${p.address} ${p.jurisdiction} ${p.meeting_body}`.toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    return true;
  }

  function render() {
    cluster.clearLayers();
    state.markerById = {};
    let shown = 0, mf = 0, upcoming = 0;
    const markers = [];
    for (const f of state.features) {
      const p = f.properties;
      if (!matches(p)) continue;
      shown++;
      if (p.multifamily) mf++;
      if (p.status === "upcoming") upcoming++;
      const m = makeMarker(f);
      state.markerById[p.id] = m;
      markers.push(m);
    }
    cluster.addLayers(markers);
    $("statMapped").textContent = shown;
    $("statMF").textContent = mf;
    $("statUpcoming").textContent = upcoming;
    if (openDrawer === "hearings") renderDrawer();
  }

  function exportCSV() {
    const cols = ["id","score","multifamily","units","acres","project_type","status","meeting_date",
                  "jurisdiction","county","meeting_body","address","parcel","title","link","first_seen"];
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

  function buildCountyChips() {
    const counts = {};
    for (const f of state.features) counts[f.properties.county] = (counts[f.properties.county] || 0) + 1;
    const el = $("countyChips");
    el.innerHTML = "";
    Object.keys(counts).sort().forEach((c) => {
      const b = document.createElement("button");
      b.className = "chip" + (state.counties.has(c) ? " on" : "");
      b.textContent = `${c} · ${counts[c]}`;
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
    for (const [key, [label, varName]] of Object.entries(TYPE_META)) {
      const lab = document.createElement("label");
      lab.className = "type-check on";
      lab.style.color = css(varName);
      lab.innerHTML = `<input type="checkbox" checked><span class="type-dot" style="background:${css(varName)}"></span>${label}`;
      lab.querySelector("input").onchange = (e) => {
        e.target.checked ? state.types.add(key) : state.types.delete(key);
        lab.classList.toggle("on", e.target.checked);
        render();
      };
      el.appendChild(lab);
    }
  }

  /* drawers */
  let openDrawer = null;
  function renderDrawer() {
    const d = $("drawer");
    if (!openDrawer) { d.hidden = true; return; }
    d.hidden = false;
    if (openDrawer === "hearings") {
      const today = new Date().toISOString().slice(0, 10);
      const horizon = new Date(); horizon.setDate(horizon.getDate() + 14);
      const hz = horizon.toISOString().slice(0, 10);
      const up = state.features.map((f) => f.properties)
        .filter((p) => matches(p) && p.meeting_date >= today && p.meeting_date <= hz)
        .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date) || (b.score || 0) - (a.score || 0));
      d.innerHTML = up.length ? up.map((p) => `
        <div class="u-item h-item" data-id="${p.id}">
          <div class="h-date">${esc(p.meeting_date)}${isNew(p) ? ' <span class="pp-chip pp-chip-new">New</span>' : ""}${p.score >= 5 ? ' <span class="pp-hot">★' + p.score + "</span>" : ""}</div>
          <a href="${esc(p.link)}" target="_blank" rel="noopener">${esc((p.plain || p.title).slice(0, 110))}</a>
          <div class="u-meta">${esc(p.jurisdiction)} · ${esc(p.meeting_body)}</div>
        </div>`).join("")
        : '<div class="u-meta" style="padding:12px 0">No hearings in the next 14 days match the current filters.</div>';
      d.querySelectorAll(".h-item").forEach((el) => {
        el.addEventListener("click", (ev) => {
          if (ev.target.tagName === "A") return;
          const m = state.markerById[el.dataset.id];
          if (m) { map.setView(m.getLatLng(), Math.max(map.getZoom(), 14)); m.openPopup(); }
        });
      });
    } else if (openDrawer === "unmapped") {
      d.innerHTML = state.unmapped.length
        ? state.unmapped.map((u) => `
          <div class="u-item">
            <a href="${esc(u.link)}" target="_blank" rel="noopener">${esc((u.plain || u.title).slice(0, 130))}</a>
            <div class="u-meta">${esc(u.jurisdiction)} · ${esc(u.meeting_date || "no date")} · no mappable address</div>
          </div>`).join("")
        : '<div class="u-meta" style="padding:12px 0">Every development item has a mapped location. 🎯</div>';
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

  /* panel collapse */
  $("collapseBtn").onclick = () => { $("panel").style.display = "none"; $("expandBtn").hidden = false; };
  $("expandBtn").onclick = () => { $("panel").style.display = ""; $("expandBtn").hidden = true; };

  /* filter inputs */
  $("search").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
  $("mfOnly").addEventListener("change", (e) => { state.mfOnly = e.target.checked; render(); });
  $("newOnly").addEventListener("change", (e) => { state.newOnly = e.target.checked; render(); });
  $("statusSel").addEventListener("change", (e) => { state.status = e.target.value; render(); });
  $("csvBtn").addEventListener("click", exportCSV);

  /* load */
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
    // entry filters from the landing page: ?county=Broward or ?region=south
    const wantCounty = params.get("county");
    const wantRegion = params.get("region");
    if (wantCounty) {
      wantCounty.split(",").forEach((c) => state.counties.add(c));
      $("brandSub").textContent = wantCounty.replace(",", " · ") + " County";
    } else if (wantRegion && REGIONS[wantRegion]) {
      REGIONS[wantRegion].counties.forEach((c) => state.counties.add(c));
      $("brandSub").textContent = REGIONS[wantRegion].name;
    }
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
    const visible = state.features.filter((f) => matches(f.properties));
    if (visible.length) {
      const b = L.geoJSON({ type: "FeatureCollection", features: visible }).getBounds();
      if (b.isValid()) map.fitBounds(b.pad(0.08));
    }
  }).catch((err) => {
    $("updatedAt").textContent = "Data failed to load — run ./refresh.sh";
    console.error(err);
  });
})();
