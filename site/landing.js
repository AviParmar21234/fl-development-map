/* Morgan Group · Florida Development Radar — landing */
(() => {
  const REGIONS = {
    south: { name: "South Florida", counties: ["Miami-Dade", "Broward", "Palm Beach"] },
    central: { name: "Central Florida", counties: ["Orange", "Osceola", "Seminole", "Lake", "Hillsborough", "Pinellas", "Polk"] },
  };
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const today = new Date().toISOString().slice(0, 10);

  Promise.all([
    fetch("data/projects.geojson").then((r) => r.json()),
    fetch("data/unmapped.json").then((r) => r.json()).catch(() => []),
    fetch("data/coverage.json").then((r) => r.json()).catch(() => []),
    fetch("data/meta.json").then((r) => r.json()).catch(() => null),
  ]).then(([fc, unmapped, coverage, meta]) => {
    const mapped = (fc.features || []).map((f) => f.properties);
    const all = [...mapped, ...unmapped];

    /* hero stats */
    $("hsProjects").textContent = all.length.toLocaleString();
    $("hsMF").textContent = all.filter((p) => p.multifamily).length.toLocaleString();
    $("hsUpcoming").textContent = all.filter((p) => p.meeting_date >= today).length.toLocaleString();
    $("hsSources").textContent = coverage.filter((c) => c.ok).length;
    if (meta) $("footUpdated").textContent = `Data refreshed ${meta.generated_at.slice(0, 16).replace("T", " ")} UTC`;

    /* per-county aggregates */
    const agg = {};
    for (const p of all) {
      const a = (agg[p.county] = agg[p.county] || { total: 0, mf: 0, upcoming: 0 });
      a.total++;
      if (p.multifamily) a.mf++;
      if (p.meeting_date >= today) a.upcoming++;
    }

    /* ticker: upcoming multifamily hearings, soonest first */
    const tseen = new Set();
    const tickerItems = all
      .filter((p) => p.multifamily && p.meeting_date >= today)
      .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
      .filter((p) => {
        const k = p.plain || p.title;
        if (tseen.has(k)) return false;
        tseen.add(k);
        return true;
      })
      .slice(0, 18);
    if (tickerItems.length) {
      const half = tickerItems.map((p) =>
        `<span class="tick-item"><span class="tick-date">${esc(p.meeting_date)}</span> · ${esc((p.plain || p.title).slice(0, 92))} <b>★${p.score || 0}</b></span>`
      ).join("");
      $("ticker").innerHTML = half + half; // duplicated for a seamless loop
    } else {
      document.querySelector(".ticker").style.display = "none";
    }

    /* region portal cards */
    const regionsEl = $("regionsGrid");
    for (const [key, r] of Object.entries(REGIONS)) {
      const counties = r.counties.filter((c) => agg[c]);
      const total = counties.reduce((s, c) => s + agg[c].total, 0);
      const mf = counties.reduce((s, c) => s + agg[c].mf, 0);
      const up = counties.reduce((s, c) => s + agg[c].upcoming, 0);
      const btn = document.createElement("button");
      btn.className = "region";
      btn.innerHTML = `
        <h3>${r.name}</h3>
        <div class="r-counties">${counties.join(" · ")}</div>
        <div class="r-nums">
          <div><b>${total.toLocaleString()}</b><i>projects</i></div>
          <div class="gold"><b>${mf.toLocaleString()}</b><i>multifamily</i></div>
          <div><b>${up.toLocaleString()}</b><i>upcoming</i></div>
        </div>
        <span class="r-go">Explore →</span>`;
      btn.onclick = () => selectRegion(key, btn);
      regionsEl.appendChild(btn);
    }

    function selectRegion(key, btn) {
      document.querySelectorAll(".region").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const r = REGIONS[key];

      /* county tiles */
      const counties = r.counties.filter((c) => agg[c]);
      $("countiesTitle").textContent = `${r.name} counties`;
      const el = $("counties");
      el.innerHTML = "";
      counties
        .sort((a, b) => agg[b].total - agg[a].total)
        .forEach((c, i) => {
          const a = agg[c];
          const card = document.createElement("a");
          card.className = "county";
          card.href = `map.html?county=${encodeURIComponent(c)}`;
          card.style.animationDelay = `${i * 45}ms`;
          card.innerHTML = `
            <h4>${esc(c)}</h4>
            <div class="c-total">${a.total.toLocaleString()}</div>
            <div class="c-label">projects</div>
            <div class="c-sub"><b>${a.mf}</b> multifamily · ${a.upcoming} upcoming</div>`;
          el.appendChild(card);
        });
      $("countiesSection").hidden = false;

      /* top opportunities in region */
      const rc = new Set(r.counties);
      const seen = new Set();
      const top = mapped
        .filter((p) => rc.has(p.county))
        .sort((a, b) => (b.score || 0) - (a.score || 0) || (b.meeting_date >= today) - (a.meeting_date >= today))
        .filter((p) => {
          const key = p.plain || p.title;  // same project at multiple hearings → one row
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        })
        .slice(0, 8);
      $("oppsSub").textContent = `${r.name} · ranked by multifamily signal`;
      const ol = $("opps");
      ol.innerHTML = "";
      top.forEach((p, i) => {
        const li = document.createElement("li");
        li.style.animationDelay = `${i * 40}ms`;
        li.innerHTML = `
          <a class="opp" href="map.html?county=${encodeURIComponent(p.county)}">
            <span class="o-num"></span>
            <span class="o-body">
              <span class="o-plain">${esc(p.plain || p.title)}</span>
              <span class="o-meta">${esc(p.jurisdiction)} · ${esc(p.meeting_body)}${p.meeting_date ? ` · hearing <b>${esc(p.meeting_date)}</b>` : ""}</span>
            </span>
            <span class="o-score">★ ${p.score || 0}</span>
          </a>`;
        ol.appendChild(li);
      });
      $("oppsSection").hidden = false;
      $("countiesSection").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }).catch((err) => {
    $("footUpdated").textContent = "Data failed to load — run ./refresh.sh";
    console.error(err);
  });
})();
