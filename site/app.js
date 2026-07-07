/* Morgan Group · Florida Development Radar — map */
(() => {
  /* 4 calm categories instead of 10 colors */
  const BUCKETS = {
    land: { label: "Rezoning & Land Use", color: "#d4593c", types: ["rezoning", "land-use", "annexation", "development-agreement"] },
    plans: { label: "Site Plans & PUD", color: "#3b6fb3", types: ["site-plan", "pud", "plat"] },
    minor: { label: "Variances & Exceptions", color: "#8a8f96", types: ["variance", "special-exception"] },
    other: { label: "Other", color: "#6d7278", types: ["other-development"] },
  };
  const TYPE_LABELS = {
    "rezoning": "Rezoning", "land-use": "Land Use", "site-plan": "Site Plan", "pud": "PUD",
    "plat": "Plat", "variance": "Variance", "special-exception": "Special Exception",
    "development-agreement": "Dev Agreement", "annexation": "Annexation", "other-development": "Other",
  };
  const bucketOf = (t) => Object.keys(BUCKETS).find((k) => BUCKETS[k].types.includes(t)) || "other";
  const typeLabel = (t) => TYPE_LABELS[t] || "Development";
  const typeColor = (t) => BUCKETS[bucketOf(t)].color;

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
    q: "", seg: "all", showArchived: false,
    counties: new Set(), buckets: new Set(Object.keys(BUCKETS)),
    features: [], unmapped: [], coverage: [],
    newCutoff: null,
    entities: {}, markerByKey: {}, entityByItemId: {},
    selectedKey: null,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const SCORE_TIP = "Opportunity score (0–8): multifamily signal + unit count + acreage + rezoning/PUD-type + hearing still ahead";
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function fmtDate(iso) {
    if (!iso || iso.length < 10) return iso || "";
    const [y, m, d] = iso.split("-").map(Number);
    const thisYear = new Date().getFullYear();
    return `${MONTHS[m - 1]} ${d}${y === thisYear ? "" : ", " + y}`;
  }

  /* ---------- local collections (persist per browser) ---------- */
  function loadSet(key) {
    try { return new Set(JSON.parse(localStorage.getItem(key) || "[]")); }
    catch { return new Set(); }
  }
  const archived = loadSet("mgRadarArchived");
  const saved = loadSet("mgRadarSaved");
  const persist = (key, set) => localStorage.setItem(key, JSON.stringify([...set]));
  const isArchived = (key) => archived.has(key);
  const isSaved = (key) => saved.has(key);

  function toggleArchive(key) {
    archived.has(key) ? archived.delete(key) : archived.add(key);
    persist("mgRadarArchived", archived);
    refreshAfterCollectionChange(key);
  }
  function toggleSave(key) {
    saved.has(key) ? saved.delete(key) : saved.add(key);
    persist("mgRadarSaved", saved);
    refreshAfterCollectionChange(key);
  }
  function refreshAfterCollectionChange(key) {
    updateCounts();
    render();
    if (state.selectedKey === key && state.entities[key]) {
      $("pcBody").innerHTML = cardHTML(state.entities[key]);
      wireCard();
    }
  }
  function updateCounts() {
    $("archCount").textContent = archived.size ? `(${archived.size})` : "";
    $("savedCount").textContent = saved.size ? `(${saved.size})` : "";
  }

  /* one address = one site */
  const ADDR_ABBR = [
    [/\bSTREET\b/g, "ST"], [/\bAVENUE\b/g, "AVE"], [/\bBOULEVARD\b/g, "BLVD"],
    [/\bROAD\b/g, "RD"], [/\bDRIVE\b/g, "DR"], [/\bCOURT\b/g, "CT"],
    [/\bTERRACE\b/g, "TER"], [/\bPLACE\b/g, "PL"], [/\bLANE\b/g, "LN"],
    [/\bHIGHWAY\b/g, "HWY"], [/\bPARKWAY\b/g, "PKWY"], [/\bCIRCLE\b/g, "CIR"],
    [/\bTRAIL\b/g, "TRL"], [/\bNORTHWEST\b/g, "NW"], [/\bNORTHEAST\b/g, "NE"],
    [/\bSOUTHWEST\b/g, "SW"], [/\bSOUTHEAST\b/g, "SE"],
  ];
  function normAddr(a) {
    let s = a.toUpperCase().replace(/[.,#]/g, " ").replace(/\s+/g, " ").trim();
    for (const [re, to] of ADDR_ABBR) s = s.replace(re, to);
    return s;
  }

  function computeNewCutoff(meta) {
    const dates = new Set(state.features.map((f) => f.properties.first_seen).filter(Boolean));
    if (dates.size <= 1) return null;
    const gen = meta ? meta.generated_at.slice(0, 10) : new Date().toISOString().slice(0, 10);
    const d = new Date(gen); d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  }
  const isNew = (p) => state.newCutoff && p.first_seen && p.first_seen >= state.newCutoff;
  const entityIsNew = (e) => state.newCutoff && e.firstSeen >= state.newCutoff;

  function buildEntities() {
    state.entities = {};
    state.entityByItemId = {};
    for (const f of state.features) {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      const key = p.address ? `a:${p.jurisdiction}|${normAddr(p.address)}`
        : p.parcel ? `p:${p.county}|${p.parcel}`
        : `c:${lat.toFixed(5)},${lon.toFixed(5)}`;
      let e = state.entities[key];
      if (!e) e = state.entities[key] = { key, lat, lon, items: [] };
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
      e.firstSeen = e.items.reduce((m, i) => (i.first_seen && i.first_seen < m ? i.first_seen : m), "9999");
    }
  }

  function matches(p) {
    if (state.seg === "mf" && !p.multifamily) return false;
    if (state.seg === "upcoming" && p.status !== "upcoming") return false;
    if (state.counties.size && !state.counties.has(p.county)) return false;
    if (!state.buckets.has(bucketOf(p.project_type))) return false;
    if (state.q) {
      const hay = `${p.title} ${p.plain || ""} ${p.address || ""} ${p.jurisdiction} ${p.meeting_body}`.toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    return true;
  }
  const visibleItems = (e) => e.items.filter(matches);
  const listable = (p) => {
    const k = state.entityByItemId[p.id];
    return matches(p) && (!k || !isArchived(k) || state.showArchived);
  };

  /* ---------- pins ---------- */
  function pinIcon(e, active) {
    const vis = visibleItems(e);
    const mf = vis.some((i) => i.multifamily);
    const fresh = vis.some((i) => isNew(i));
    const heart = isSaved(e.key);
    const best = [...vis].sort((a, b) => (b.score || 0) - (a.score || 0))[0] || e.best;
    const color = typeColor(best && best.project_type);
    const w = mf ? 30 : 24, h = mf ? 40 : 32;
    const stroke = active ? "#1a1c1f" : (mf ? "#26282c" : "#ffffff");
    return L.divIcon({
      className: "pin-wrap" + (active ? " pin-active" : ""),
      html: `<svg width="${w}" height="${h}" viewBox="0 0 30 40">
        <path d="M15 1 C7 1 1.5 7 1.5 14.5 C1.5 24 15 39 15 39 C15 39 28.5 24 28.5 14.5 C28.5 7 23 1 15 1 Z"
              fill="${color}" stroke="${stroke}" stroke-width="${active ? 2.6 : (mf ? 2.2 : 1.6)}"/>
        <circle cx="15" cy="14.5" r="5" fill="#ffffff"/>
        ${heart ? '<path transform="translate(1,1) scale(0.62)" d="M8 4 C6 1.6 2.6 2 1.6 4.4 C.6 6.8 2.4 9 8 13 C13.6 9 15.4 6.8 14.4 4.4 C13.4 2 10 1.6 8 4 Z" fill="#c0392b" stroke="#fff" stroke-width="1.6"/>' : ""}
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
      const arch = isArchived(e.key);
      if (arch && !state.showArchived) continue;
      const vis = visibleItems(e);
      if (!vis.length) continue;
      if (!arch) {
        sites++;
        if (vis.some((i) => i.multifamily)) mf++;
        if (vis.some((i) => i.status === "upcoming")) upcoming++;
      }
      const m = L.marker([e.lat, e.lon], {
        icon: pinIcon(e, e.key === state.selectedKey),
        riseOnHover: true,
        opacity: arch ? 0.45 : 1,
      });
      m.bindTooltip(esc(e.address || e.parcel || e.jurisdiction) + (arch ? " (archived)" : ""), { direction: "top", opacity: 0.95 });
      m.on("click", () => selectEntity(e.key, false));
      m.addTo(pinLayer);
      state.markerByKey[e.key] = m;
    }
    $("statMapped").textContent = sites;
    $("statMF").textContent = mf;
    $("statUpcoming").textContent = upcoming;
    updateBadges();
    if (state.selectedKey && !state.markerByKey[state.selectedKey] && !isArchived(state.selectedKey)) closeCard();
    if (openDrawer) renderDrawer();
  }

  /* tab badges always count exactly what their lists show, filters included */
  function updateBadges() {
    const today = new Date().toISOString().slice(0, 10);
    const hz = new Date(); hz.setDate(hz.getDate() + 14);
    const hzs = hz.toISOString().slice(0, 10);
    const nHear = state.features.map((f) => f.properties)
      .filter((p) => listable(p) && p.meeting_date >= today && p.meeting_date <= hzs).length;
    $("hearingsCount").textContent = nHear ? `(${nHear})` : "";
    const nFresh = state.newCutoff
      ? visibleEntities().filter((e) => entityIsNew(e)).length : 0;
    $("latestCount").textContent = nFresh ? `(${nFresh})` : "";
  }

  /* ---------- property card ---------- */
  function cardHTML(e) {
    const vis = visibleItems(e);
    const mf = vis.some((i) => i.multifamily);
    const units = Math.max(0, ...vis.map((i) => i.units || 0));
    const acres = Math.max(0, ...vis.map((i) => i.acres || 0));
    const score = Math.max(0, ...vis.map((i) => i.score || 0));
    const facts = [
      units ? `${units} units` : "",
      acres ? `${acres} ac` : "",
      score ? `<span title="${SCORE_TIP}">★ ${score}/8</span>` : "",
    ].filter(Boolean).join(" · ");
    const itemRow = (i) => `
      <div class="pc-item">
        <div class="pc-item-head">
          <span class="pc-type"><i class="pc-type-dot" style="background:${typeColor(i.project_type)}"></i>${typeLabel(i.project_type)}</span>
          ${i.multifamily ? '<span class="pc-type pc-type-mf">Multifamily</span>' : ""}
          ${isNew(i) ? '<span class="pc-type pc-type-new">New</span>' : ""}
          <span class="pc-date">${fmtDate(i.meeting_date)}${i.status === "upcoming" ? " · upcoming" : ""}</span>
        </div>
        <p class="pc-plain">${esc(i.plain || i.title)}</p>
        <div class="pc-meta">${esc(i.meeting_body)} · <a href="${esc(i.link)}" target="_blank" rel="noopener">View source →</a></div>
      </div>`;
    const types = [...new Set(vis.map((i) => i.project_type))];
    const rows = types.length > 1
      ? types.map((t) => `
          <div class="pc-plan">
            <div class="pc-plan-head"><i class="pc-type-dot" style="background:${typeColor(t)}"></i>${typeLabel(t)} plan</div>
            ${vis.filter((i) => i.project_type === t).map(itemRow).join("")}
          </div>`).join("")
      : vis.map(itemRow).join("");
    const arch = isArchived(e.key);
    const sv = isSaved(e.key);
    return `
      <p class="pc-kicker">${mf ? "Multifamily site" : "Development site"} · ${esc(e.county)} County${arch ? " · <b class='pc-arch-flag'>Archived</b>" : ""}</p>
      <h2 class="pc-title">${esc(e.address || (e.parcel ? "Parcel " + e.parcel : e.jurisdiction))}</h2>
      <p class="pc-sub">${esc(e.jurisdiction)}${facts ? ` · ${facts}` : ""}</p>
      <div class="pc-actions">
        <button class="pc-btn ${sv ? "pc-btn-saved" : ""}" id="pcSave" data-key="${esc(e.key)}">${sv ? "♥ Saved" : "♡ Save"}</button>
        <button class="pc-btn" id="pcArchive" data-key="${esc(e.key)}">${arch ? "⤴ Restore" : "🗂 Archive"}</button>
      </div>
      <div class="pc-items">${rows}</div>`;
  }
  function wireCard() {
    const a = $("pcArchive");
    if (a) a.onclick = () => toggleArchive(a.dataset.key);
    const s = $("pcSave");
    if (s) s.onclick = () => toggleSave(s.dataset.key);
  }

  function selectEntity(key, fly) {
    const prev = state.selectedKey;
    state.selectedKey = key;
    const e = state.entities[key];
    if (prev && state.markerByKey[prev]) state.markerByKey[prev].setIcon(pinIcon(state.entities[prev], false));
    if (state.markerByKey[key]) state.markerByKey[key].setIcon(pinIcon(e, true));
    $("pcBody").innerHTML = cardHTML(e);
    wireCard();
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
  document.querySelectorAll("#seg button").forEach((b) => {
    b.onclick = () => {
      state.seg = b.dataset.seg;
      document.querySelectorAll("#seg button").forEach((x) => x.classList.toggle("on", x === b));
      render();
    };
  });

  function updateContext() {
    const sel = [...state.counties];
    for (const r of Object.values(REGIONS)) {
      if (sel.length === r.counties.length && r.counties.every((c) => state.counties.has(c))) {
        $("brandSub").textContent = r.name;
        return;
      }
    }
    $("brandSub").textContent =
      sel.length === 0 ? "Florida Development Radar"
      : sel.length === 1 ? `${sel[0]} County`
      : `${sel.length} counties`;
  }

  function buildCountyChips() {
    const counts = {};
    for (const f of state.features) counts[f.properties.county] = (counts[f.properties.county] || 0) + 1;
    const el = $("countyChips");
    el.innerHTML = "";
    const reset = document.createElement("button");
    reset.className = "chip chip-reset";
    reset.textContent = "✕ All counties";
    reset.title = "Clear the county filter";
    reset.onclick = () => {
      state.counties.clear();
      buildCountyChips();
      updateContext();
      render();
    };
    Object.keys(counts).sort().forEach((c) => {
      const b = document.createElement("button");
      b.className = "chip" + (state.counties.has(c) ? " on" : "");
      b.textContent = c;
      b.onclick = () => {
        state.counties.has(c) ? state.counties.delete(c) : state.counties.add(c);
        b.classList.toggle("on");
        reset.style.display = state.counties.size ? "" : "none";
        updateContext();
        render();
      };
      el.appendChild(b);
    });
    reset.style.display = state.counties.size ? "" : "none";
    el.appendChild(reset);
  }

  function buildTypeChecks() {
    const el = $("typeChecks");
    el.innerHTML = "";
    for (const [key, b] of Object.entries(BUCKETS)) {
      const lab = document.createElement("label");
      lab.className = "type-check on";
      lab.innerHTML = `<input type="checkbox" checked><span class="type-dot" style="--tc:${b.color}"></span>${b.label}`;
      lab.querySelector("input").onchange = (ev) => {
        ev.target.checked ? state.buckets.add(key) : state.buckets.delete(key);
        lab.classList.toggle("on", ev.target.checked);
        render();
      };
      el.appendChild(lab);
    }
  }

  /* ---------- drawers ---------- */
  let openDrawer = null;
  function entityRow(e, extra) {
    const best = visibleItems(e)[0] ? [...visibleItems(e)].sort((a, b) => (b.score || 0) - (a.score || 0))[0] : e.best;
    return `
      <div class="u-item p-item" data-key="${esc(e.key)}">
        ${isSaved(e.key) ? '<span class="u-heart">♥</span> ' : ""}<a href="${esc(best.link)}" target="_blank" rel="noopener">${esc((best.plain || best.title).slice(0, 110))}</a>
        <div class="u-meta">${esc(e.jurisdiction)}${extra || ""} · <span title="${SCORE_TIP}">★ ${best.score || 0}</span></div>
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
  function visibleEntities() {
    return Object.values(state.entities).filter((e) =>
      visibleItems(e).length && (!isArchived(e.key) || state.showArchived));
  }
  function renderDrawer() {
    const d = $("drawer");
    if (!openDrawer) { d.hidden = true; return; }
    d.hidden = false;
    if (openDrawer === "projects") {
      const ranked = visibleEntities()
        .sort((a, b) => (b.best.score || 0) - (a.best.score || 0) || (b.best.meeting_date || "").localeCompare(a.best.meeting_date || ""))
        .slice(0, 60);
      d.innerHTML = ranked.length ? ranked.map((e) => entityRow(e)).join("")
        : '<div class="u-meta" style="padding:12px 0">No sites match the current filters.</div>';
      wireRows(d);
    } else if (openDrawer === "latest") {
      if (!state.newCutoff) {
        d.innerHTML = `<div class="u-note">
          <b>How “New” works</b><br>
          The radar re-scans all ${state.coverage.length || 44} public sources every night around 4–5 AM ET.
          Any site it has never seen before lands here the next morning, newest first, and its pin
          gets a green dot for a week. Cities publish agendas on their own cycles — most boards post
          3–7 days before a hearing — so expect a fresh batch most weekday mornings.<br><br>
          <span>This dataset is from the first scan, so everything is technically “new.” Check back after tomorrow's refresh.</span>
        </div>`;
        return;
      }
      const fresh = visibleEntities()
        .filter((e) => entityIsNew(e))
        .sort((a, b) => b.firstSeen.localeCompare(a.firstSeen))
        .slice(0, 80);
      d.innerHTML = fresh.length
        ? '<div class="d-hint">First discovered in the last 7 days — their hearings may be past or future.</div>'
          + fresh.map((e) => entityRow(e, ` · added ${fmtDate(e.firstSeen)}`)).join("")
        : '<div class="u-meta" style="padding:12px 0">Nothing new in the last 7 days for these filters. The radar re-scans nightly around 4–5 AM ET.</div>';
      wireRows(d);
    } else if (openDrawer === "saved") {
      const rows = Object.values(state.entities)
        .filter((e) => isSaved(e.key))
        .sort((a, b) => (b.best.meeting_date || "").localeCompare(a.best.meeting_date || ""));
      d.innerHTML = rows.length ? rows.map((e) => entityRow(e)).join("")
        : '<div class="u-meta" style="padding:12px 0">No saved sites yet — open a pin and tap ♡ Save to track it here.</div>';
      wireRows(d);
    } else if (openDrawer === "hearings") {
      const today = new Date().toISOString().slice(0, 10);
      const horizon = new Date(); horizon.setDate(horizon.getDate() + 14);
      const hz = horizon.toISOString().slice(0, 10);
      const up = state.features.map((f) => f.properties)
        .filter((p) => listable(p) && p.meeting_date >= today && p.meeting_date <= hz)
        .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date) || (b.score || 0) - (a.score || 0));
      d.innerHTML = up.length ? '<div class="d-hint">Hearings on the calendar in the next 14 days.</div>' + up.map((p) => `
        <div class="u-item p-item" data-key="${state.entityByItemId[p.id] || ""}">
          <div class="h-date">${fmtDate(p.meeting_date)}</div>
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
            <div class="u-meta">${esc(u.jurisdiction)} · ${u.meeting_date ? fmtDate(u.meeting_date) : "no date"} · no mappable address</div>
          </div>`).join("")
        : '<div class="u-meta" style="padding:12px 0">Every development item has a mapped location.</div>';
    } else {
      d.innerHTML = '<div class="d-hint">Every public portal scanned nightly — kept = items classified as real development activity.</div>'
        + state.coverage.map((c) => `
        <div class="cov-row">
          <b>${esc(c.name)}</b>
          <span>${c.ok ? `<span class="cov-ok">${c.items_dev} kept · ${c.items_raw} scanned</span>` : `<span class="cov-err" title="${esc(c.error || "")}">failed</span>`}</span>
        </div>`).join("");
    }
  }
  document.querySelectorAll(".drawer-tabs button, .drawer-foot button").forEach((btn) => {
    btn.onclick = () => {
      openDrawer = openDrawer === btn.dataset.drawer ? null : btn.dataset.drawer;
      document.querySelectorAll(".drawer-tabs button, .drawer-foot button").forEach((b) =>
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
  $("showArchived").addEventListener("change", (e) => { state.showArchived = e.target.checked; render(); });

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
  const grab = (u) => fetch(u, { cache: "no-cache" });  // always revalidate data
  Promise.all([
    grab("data/projects.geojson").then((r) => r.json()),
    grab("data/unmapped.json").then((r) => r.json()).catch(() => []),
    grab("data/coverage.json").then((r) => r.json()).catch(() => []),
    grab("data/meta.json").then((r) => r.json()).catch(() => null),
  ]).then(([fc, unmapped, coverage, meta]) => {
    state.features = fc.features || [];
    state.unmapped = unmapped;
    state.coverage = coverage;
    state.newCutoff = computeNewCutoff(meta);
    const wantCounty = params.get("county");
    const wantRegion = params.get("region");
    if (wantCounty) {
      wantCounty.split(",").forEach((c) => state.counties.add(c));
    } else if (wantRegion && REGIONS[wantRegion]) {
      REGIONS[wantRegion].counties.forEach((c) => state.counties.add(c));
    }
    updateContext();
    buildEntities();
    buildCountyChips();
    buildTypeChecks();
    updateCounts();
    render();
    $("unmappedCount").textContent = unmapped.length ? `(${unmapped.length})` : "";
    $("coverageCount").textContent = coverage.length ? `(${coverage.length})` : "";
    updateBadges();
    if (meta) $("updatedAt").textContent = `Updated ${meta.generated_at.slice(0, 16).replace("T", " ")} UTC · public-record sources`;
    const visible = visibleEntities();
    if (visible.length) {
      const b = L.latLngBounds(visible.map((e) => [e.lat, e.lon]));
      if (b.isValid()) map.fitBounds(b.pad(0.08));
    }
    const wantTab = params.get("tab");
    openDrawer = ["latest", "hearings", "saved", "projects"].includes(wantTab) ? wantTab : "projects";
    document.querySelectorAll(".drawer-tabs button, .drawer-foot button").forEach((b) =>
      b.classList.toggle("active", b.dataset.drawer === openDrawer));
    renderDrawer();
  }).catch((err) => {
    $("updatedAt").textContent = "Data failed to load — run ./refresh.sh";
    console.error(err);
  });
})();
