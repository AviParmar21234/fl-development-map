/* Morgan Group · Florida Development Radar — home */
(() => {
  const REGIONS = {
    south: { name: "South Florida", counties: ["Miami-Dade", "Broward", "Palm Beach"] },
    central: { name: "Central Florida", counties: ["Orange", "Osceola", "Seminole", "Lake", "Hillsborough", "Pinellas", "Polk"] },
  };
  const BUCKET_COLORS = {
    "rezoning": "#d4593c", "land-use": "#d4593c", "annexation": "#d4593c", "development-agreement": "#d4593c",
    "site-plan": "#3b6fb3", "pud": "#3b6fb3", "plat": "#3b6fb3",
    "variance": "#8a8f96", "special-exception": "#8a8f96",
    "other-development": "#6d7278",
  };
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const today = new Date().toISOString().slice(0, 10);

  /* ---------- the cinematic backdrop: the real data, slowly drifting ---------- */
  const bg = L.map("bgmap", {
    zoomControl: false, dragging: false, scrollWheelZoom: false,
    doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false,
    attributionControl: false,
  }).setView([25.85, -80.25], 10);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    subdomains: "abcd", maxZoom: 19,
  }).addTo(bg);

  const TOUR = [
    [25.82, -80.22, 11],  // Miami
    [26.10, -80.16, 11],  // Fort Lauderdale
    [26.66, -80.09, 11],  // West Palm Beach
    [28.02, -82.50, 10],  // Tampa Bay
    [28.50, -81.38, 10],  // Orlando
  ];
  let leg = 0;
  function drift() {
    leg = (leg + 1) % TOUR.length;
    const [lat, lon, z] = TOUR[leg];
    bg.flyTo([lat, lon], z, { duration: 26, easeLinearity: 0.12 });
  }
  bg.whenReady(() => setTimeout(drift, 2500));
  bg.on("moveend", () => setTimeout(drift, 1800));

  /* ---------- data ---------- */
  Promise.all([
    fetch("data/projects.geojson").then((r) => r.json()),
    fetch("data/unmapped.json").then((r) => r.json()).catch(() => []),
    fetch("data/coverage.json").then((r) => r.json()).catch(() => []),
    fetch("data/meta.json").then((r) => r.json()).catch(() => null),
  ]).then(([fc, unmapped, coverage, meta]) => {
    const mapped = (fc.features || []).map((f) => f.properties);
    const all = [...mapped, ...unmapped];

    /* pins on the backdrop (canvas for perf, tiny and quiet) */
    const canvas = L.canvas({ padding: 0.4 });
    for (const f of fc.features || []) {
      const [lon, lat] = f.geometry.coordinates;
      const p = f.properties;
      L.circleMarker([lat, lon], {
        renderer: canvas,
        radius: p.multifamily ? 4.5 : 3,
        color: "#ffffff", weight: 1,
        fillColor: BUCKET_COLORS[p.project_type] || "#6d7278",
        fillOpacity: 0.85,
      }).addTo(bg);
    }

    /* one quiet stats line */
    const mf = all.filter((p) => p.multifamily).length;
    const up = all.filter((p) => p.meeting_date >= today).length;
    const srcs = coverage.filter((c) => c.ok).length;
    $("statline").innerHTML =
      `<b>${all.length.toLocaleString()}</b> active projects · <b>${mf.toLocaleString()}</b> multifamily · ` +
      `<b>${up.toLocaleString()}</b> upcoming hearings — updated nightly from ${srcs} public sources`;

    /* county directory */
    const agg = {};
    for (const p of all) {
      const a = (agg[p.county] = agg[p.county] || { total: 0, mf: 0 });
      a.total++;
      if (p.multifamily) a.mf++;
    }
    function fill(elId, counties) {
      const el = $(elId);
      counties
        .filter((c) => agg[c])
        .sort((a, b) => agg[b].total - agg[a].total)
        .forEach((c) => {
          const a = document.createElement("a");
          a.href = `map.html?county=${encodeURIComponent(c)}`;
          a.innerHTML = `<span class="d-n">${esc(c)}</span>` +
            `<span class="d-c">${agg[c].total.toLocaleString()}</span>` +
            (agg[c].mf ? `<span class="d-mf">${agg[c].mf} MF</span>` : "");
          el.appendChild(a);
        });
    }
    fill("southList", REGIONS.south.counties);
    fill("centralList", REGIONS.central.counties);
  }).catch((err) => {
    $("statline").textContent = "Data failed to load — run ./refresh.sh";
    console.error(err);
  });
})();
