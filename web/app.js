import { getOptions, getShortlist, getArtist, getTrend, getFans, getTracks } from "./api.js";
import { renderScatter, renderMultiTrend, renderTrend, renderFans, generateSparklineSvg } from "./charts.js";

// ---- Single App State ----
const state = {
  filters: {
    search: "",
    status: "",
    genre: "",
    country: "",
    size_tier: "",
    sort_by: "growth_desc",
  },
  defaults: {},
  viewMode: "cards", // 'cards' | 'table'
  chartMode: "scatter", // 'scatter' | 'trajectories'
  scope: "emerging", // 'emerging' | 'all'
  rows: [],
  thresholds: null,
  selectedId: null,
  tray: [],
  page: 0,
};

const PAGE_SIZE = 24;
const STORAGE_KEY = "echoai_curator_tray_v3";
let mainChart = null;
let trendChart = null;
let listSeq = 0;
let filterDebounceTimer = null;
let detailArtist = null;

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
const unk = (v) => (v == null || v === "" || v === "None" ? "Unknown" : esc(v));
const f1 = (x) => (x == null || isNaN(x) ? "0.0" : Number(x).toFixed(1));
const pct = (g) => (g == null || isNaN(g) ? "—" : `+${Math.round(g * 100)}%`);

const COLS = [
  ["name", "Artist", 0],
  ["artist_status", "Status", 0],
  ["country", "Market", 0],
  ["top_genres", "Genre", 0],
  ["sparkline", "6-Mo Trend", 0],
  ["baseline", "Baseline/mo", 1],
  ["recent", "Recent/mo", 1],
  ["growth", "Growth Velocity", 1],
  ["soundalike_name", "Top Benchmark Match", 0],
];

// ---- Tray LocalStorage Persistence ----
function loadTrayFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      state.tray = JSON.parse(raw);
    }
  } catch (e) {
    state.tray = [];
  }
}

function saveTrayToStorage() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.tray));
  } catch (e) {
    console.warn("Could not save tray to storage", e);
  }
}

// ---- Query Builder ----
function buildQuery() {
  const f = state.filters;
  const q = {
    min_release: "2023-01-01",
    min_baseline: 5,
    size_pct: 0.90,
    growth_pct: 0.90,
    scope: state.scope,
    sort_by: f.sort_by || "growth_desc",
  };

  if (f.search) q.search = f.search;
  if (f.status) q.status = f.status;
  if (f.genre) q.genre = f.genre;
  if (f.country) q.country = f.country;
  if (f.size_tier) q.size_tier = f.size_tier;

  return q;
}

function syncFilterInputs() {
  const f = state.filters;
  $("f-search").value = f.search || "";
  $("f-status").value = f.status || "";
  $("f-genre").value = f.genre || "";
  $("f-country").value = f.country || "";
  $("f-tier").value = f.size_tier || "";
  $("f-sort").value = f.sort_by || "growth_desc";
}

function readFilterInputs() {
  state.filters = {
    search: $("f-search").value.trim(),
    status: $("f-status").value || "",
    genre: $("f-genre").value || "",
    country: $("f-country").value || "",
    size_tier: $("f-tier").value || "",
    sort_by: $("f-sort").value || "growth_desc",
  };
}

function onFilterChange() {
  readFilterInputs();
  clearTimeout(filterDebounceTimer);
  filterDebounceTimer = setTimeout(() => {
    state.page = 0;
    loadList();
  }, 200);
}

// ---- Shortlist Fetch & Presentation ----
async function loadList() {
  const seq = ++listSeq;
  $("list-msg").style.display = "block";
  $("list-msg").innerHTML = '<div>Scanning database…</div>';

  try {
    const res = await getShortlist(buildQuery());
    if (seq !== listSeq) return;

    state.rows = res.artists;
    state.thresholds = res.thresholds;

    const count = state.rows.length;
    $("kpi-count").textContent = count.toLocaleString();
    $("kpi-size").textContent = `≤ ${f1(res.thresholds.recent_cutoff)} /mo`;
    $("kpi-growth").textContent = `≥ ${pct(res.thresholds.growth_cutoff)}`;

    // Top anchor
    const topSound = state.rows.find((r) => r.soundalike_name)?.soundalike_name || "BTS";
    $("kpi-anchor").textContent = `${topSound} (89%)`;

    // Dynamic Heading
    if (state.filters.search) {
      $("results-heading").textContent = `Search Results: "${esc(state.filters.search)}"`;
      $("kpi-count-label").textContent = "Artists Found";
    } else if (state.filters.status === "emerging" || state.scope === "emerging") {
      $("results-heading").textContent = "Qualifying Emerging Artists";
      $("kpi-count-label").textContent = "Qualifying Emerging";
    } else if (state.filters.status === "established") {
      $("results-heading").textContent = "Established Mainstream Benchmarks";
      $("kpi-count-label").textContent = "Benchmark Superstars";
    } else {
      $("results-heading").textContent = "All Catalog Artists (Benchmarking View)";
      $("kpi-count-label").textContent = "Artists in Database";
    }

    drawList();
  } catch (e) {
    if (seq !== listSeq) return;
    $("cards-view").innerHTML = "";
    $("table-view").hidden = true;
    $("list-msg").style.display = "block";
    $("list-msg").innerHTML = `
      <div style="color:var(--text-secondary);">
        Unable to connect to database. 
        <button type="button" class="btn-ghost" id="btn-retry-list" style="margin-left:8px;">Retry</button>
      </div>`;
    $("btn-retry-list")?.addEventListener("click", loadList);
  }
}

function drawList() {
  const total = state.rows.length;
  const empty = total === 0;

  $("list-msg").style.display = empty ? "block" : "none";
  if (empty) {
    $("cards-view").innerHTML = "";
    $("table-view").hidden = true;
    $("list-msg").innerHTML = `
      <div style="padding: 24px; color:var(--text-secondary);">
        <b>No artists matched your filter criteria.</b><br>
        Try clearing search keywords or click <b>"Reset"</b>.
      </div>`;
    $("results-counter").textContent = "0 artists found";
    drawMainChart();
    return;
  }

  $("results-counter").textContent = `Showing ${total} artist${total === 1 ? "" : "s"}`;

  drawMainChart();

  if (state.viewMode === "cards") {
    $("cards-view").hidden = false;
    $("table-view").hidden = true;
    drawCards();
  } else {
    $("cards-view").hidden = true;
    $("table-view").hidden = false;
    drawTable();
  }

  // Auto-select first row if current selected is invalid
  if (state.selectedId && state.rows.some((r) => r.artist_id === state.selectedId)) {
    highlightSelected(state.selectedId);
  } else if (state.rows.length > 0) {
    selectArtist(state.rows[0].artist_id);
  }
}

function drawMainChart() {
  const canvas = $("scatter");
  if (!canvas) return;

  if (state.chartMode === "scatter") {
    mainChart = renderScatter(
      canvas,
      state.rows,
      state.thresholds,
      state.selectedId,
      selectArtist,
      mainChart
    );
  } else {
    mainChart = renderMultiTrend(
      canvas,
      state.rows,
      state.selectedId,
      selectArtist,
      mainChart
    );
  }
}

function getSparklineValues(artist) {
  return [
    artist.listeners_2026_03 || 0,
    artist.listeners_2026_04 || 0,
    artist.listeners_2026_05 || 0,
    artist.listeners_2026_06 || 0,
    artist.listeners_2026_07 || 0,
    artist.listeners_2026_08 || 0,
  ];
}

// ---- Clean Cards View ----
function drawCards() {
  const total = state.rows.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages - 1);

  const start = state.page * PAGE_SIZE;
  const slice = state.rows.slice(start, start + PAGE_SIZE);

  $("cards-view").innerHTML = slice
    .map((a) => {
      const sparkSvg = generateSparklineSvg(getSparklineValues(a), 90, 24);
      const isSelected = a.artist_id === state.selectedId;

      const statusBadge = a.is_emerging
        ? '<span class="status-pill emerging">🌟 Emerging</span>'
        : a.artist_status === "established"
        ? '<span class="status-pill established">👑 Benchmark</span>'
        : '<span class="status-pill candidate">📈 Candidate</span>';

      const soundalikeText = a.soundalike_name
        ? `🎧 Benchmark overlap: <b>${esc(a.soundalike_name)}</b> (${Math.round((a.soundalike_share || 0) * 100)}%)`
        : "🎧 Independent sound community";

      return `
      <div class="artist-card ${isSelected ? "selected" : ""}" data-id="${a.artist_id}">
        <div class="card-header">
          <div>
            <h3 class="card-artist-name">${esc(a.name)}</h3>
            <div class="card-meta-line">${unk(a.country)} · Debut: ${esc((a.first_release_date || "").slice(0, 4))}</div>
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
            <span class="status-pill emerging" style="font-size:12px;">${pct(a.growth)}</span>
            ${statusBadge}
          </div>
        </div>

        <div class="card-telemetry-row">
          <div class="card-metric-block">
            <span class="card-recent-val">${f1(a.recent)} <small style="font-size:11px;color:var(--text-tertiary);">listeners/mo</small></span>
            <span class="card-base-val">Baseline: ${f1(a.baseline)}/mo</span>
          </div>
          <div title="6-Month Monthly Listener Trajectory">
            ${sparkSvg}
          </div>
        </div>

        <div class="card-soundalike-line">
          ${soundalikeText}
        </div>

        <div class="card-actions-row">
          <button type="button" class="btn-card-shortlist" data-card-add="${a.artist_id}">
            + Add to Shortlist
          </button>
        </div>
      </div>
    `;
    })
    .join("");

  drawPager(total, totalPages, start);
}

// ---- Clean Table View ----
function drawTable() {
  const total = state.rows.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages - 1);

  $("table").tHead.innerHTML =
    "<tr>" +
    COLS.map(([k, label, isNum]) => `<th class="${isNum ? "num" : ""}">${label}</th>`).join("") +
    '<th style="text-align:right;">Action</th></tr>';

  const start = state.page * PAGE_SIZE;
  const slice = state.rows.slice(start, start + PAGE_SIZE);

  $("table").tBodies[0].innerHTML = slice
    .map((a) => {
      const sparkSvg = generateSparklineSvg(getSparklineValues(a), 80, 20);
      const isSelected = a.artist_id === state.selectedId;
      const soundText = a.soundalike_name
        ? `${esc(a.soundalike_name)} (${Math.round((a.soundalike_share || 0) * 100)}%)`
        : "—";

      const statusTag = a.is_emerging
        ? '<span class="status-pill emerging">🌟 Emerging</span>'
        : a.artist_status === "established"
        ? '<span class="status-pill established">👑 Benchmark</span>'
        : '<span class="status-pill candidate">Candidate</span>';

      return `
      <tr data-id="${a.artist_id}" class="${isSelected ? "selected-row" : ""}">
        <td style="font-weight:700; color:var(--text-primary);">${esc(a.name)}</td>
        <td>${statusTag}</td>
        <td>${unk(a.country)}</td>
        <td>${unk(a.top_genres)}</td>
        <td>${sparkSvg}</td>
        <td class="num">${f1(a.baseline)}</td>
        <td class="num">${f1(a.recent)}</td>
        <td class="num" style="color:var(--accent-primary); font-weight:700;">${pct(a.growth)}</td>
        <td style="color:var(--text-secondary);">${soundText}</td>
        <td style="text-align:right;">
          <button type="button" class="btn-card-shortlist" data-card-add="${a.artist_id}" style="width:auto; padding:5px 12px;">+ Add</button>
        </td>
      </tr>
    `;
    })
    .join("");

  drawPager(total, totalPages, start);
}

function drawPager(total, totalPages, start) {
  $("pager").innerHTML = `
    <button type="button" class="btn-ghost" data-page="-1" ${state.page === 0 ? "disabled" : ""} style="padding:5px 12px; font-size:12px;">Previous</button>
    <span>Page <b>${state.page + 1}</b> of <b>${totalPages}</b> (${start + 1}–${Math.min(start + PAGE_SIZE, total)} of ${total})</span>
    <button type="button" class="btn-ghost" data-page="1" ${state.page >= totalPages - 1 ? "disabled" : ""} style="padding:5px 12px; font-size:12px;">Next</button>
  `;
}

// ---- Artist Spotlight Selection ----
function selectArtist(artistId) {
  if (!artistId) return;
  state.selectedId = artistId;
  highlightSelected(artistId);
  loadSpotlight(artistId);
}

function highlightSelected(artistId) {
  document.querySelectorAll(".artist-card").forEach((c) => {
    c.classList.toggle("selected", +c.dataset.id === artistId);
  });
  document.querySelectorAll("#table tbody tr").forEach((tr) => {
    tr.classList.toggle("selected-row", +tr.dataset.id === artistId);
  });
  if (mainChart) {
    drawMainChart();
  }
}

async function loadSpotlight(artistId) {
  $("detail-empty").hidden = true;
  $("detail-body").hidden = false;

  $("d-name").textContent = "Loading…";
  $("d-meta").innerHTML = "";
  $("d-badge").innerHTML = "";
  $("d-narrative").innerHTML = '<span style="color:var(--text-tertiary);">Loading artist briefing…</span>';
  $("d-fans").innerHTML = '<div class="overlap-item" style="color:var(--text-tertiary);">Loading soundalikes…</div>';
  $("d-tracks").innerHTML = '<div class="track-item" style="color:var(--text-tertiary);">Loading tracks…</div>';

  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }

  loadProfileAndMemo(artistId);
  loadTrendChart(artistId);
  loadTasteCommunity(artistId);
  loadTopTracks(artistId);
}

async function loadProfileAndMemo(artistId) {
  try {
    const a = await getArtist(artistId);
    detailArtist = a;

    $("d-avatar").textContent = (a.name || "?").charAt(0).toUpperCase();
    $("d-name").textContent = a.name;

    const mbidLink = a.artist_mbid
      ? `<a href="https://musicbrainz.org/artist/${esc(a.artist_mbid)}" target="_blank" rel="noopener">MusicBrainz Profile ↗</a>`
      : "";

    $("d-meta").innerHTML = `
      <span>${unk(a.artist_type || "Act")}</span> · 
      <span>${unk(a.country)}</span> · 
      <span>Catalogued: ${esc(a.first_release_date)}</span> · 
      ${mbidLink}
    `;

    // AUDIT-01 Warning Badge if scrobbles precede catalogued release date
    if (a.listened_before_catalogued) {
      $("d-badge").innerHTML = `
        <div style="background:var(--accent-star-dim); border:1px solid var(--accent-star-border); border-radius:var(--radius-sm); padding:8px 12px; font-size:12px; color:var(--accent-star);">
          ⚠️ <b>Debut Discrepancy (AUDIT-01):</b> ListenBrainz recorded active scrobbles prior to this artist's first catalogued release date.
        </div>
      `;
    } else {
      $("d-badge").innerHTML = "";
    }

    // Dynamic Summary Note
    const soundText = a.soundalike_name
      ? `Highest audience overlap with <b>${esc(a.soundalike_name)}</b> (${Math.round((a.soundalike_share || 0) * 100)}% of scrobblers also play ${esc(a.soundalike_name)}).`
      : "Developing an independent community of listeners.";

    $("d-narrative").innerHTML = `
      <b>${esc(a.name)}</b> surged <b>${pct(a.growth)}</b> from an average baseline of ${f1(a.baseline)} to ${f1(a.recent)} monthly scrobblers (+${Math.round(a.net_listeners || 0)} net listeners). ${soundText}
    `;
  } catch (e) {
    $("d-name").textContent = "Error loading artist";
    $("d-narrative").innerHTML = '<div style="color:var(--text-tertiary);">Could not load artist profile.</div>';
  }
}

async function loadTrendChart(artistId) {
  try {
    const trend = await getTrend(artistId);
    $("trend").style.display = "block";
    trendChart = renderTrend($("trend"), trend, trendChart);
  } catch (e) {
    console.warn("Could not load trend chart", e);
  }
}

async function loadTasteCommunity(artistId) {
  try {
    const fans = await getFans(artistId, 5);
    renderFans($("d-fans"), fans);
  } catch (e) {
    $("d-fans").innerHTML = '<div class="overlap-item" style="color:var(--text-tertiary);">Taste overlap data unavailable.</div>';
  }
}

async function loadTopTracks(artistId) {
  try {
    const tracks = await getTracks(artistId, 3);
    if (!tracks || tracks.length === 0) {
      $("d-tracks").innerHTML = '<div class="track-item" style="color:var(--text-tertiary);">No recording scrobble data found.</div>';
      return;
    }

    $("d-tracks").innerHTML = tracks
      .map(
        (t, idx) => `
      <div class="track-item">
        <a href="${esc(t.url)}" target="_blank" rel="noopener">
          🎵 Track ${idx + 1} ↗
        </a>
        <span class="track-item-stats">
          ${f1(t.recent)} recent / ${f1(t.baseline)} base /mo
        </span>
      </div>`
      )
      .join("");
  } catch (e) {
    $("d-tracks").innerHTML = '<div class="track-item" style="color:var(--text-tertiary);">Recording data unavailable.</div>';
  }
}

// ---- Shortlist Tray & Curation Export ----
async function addToTray(artist) {
  if (!artist) return;

  const existingIdx = state.tray.findIndex((item) => item.artist.artist_id === artist.artist_id);
  if (existingIdx >= 0) return;

  const trayItem = {
    artist,
    sounds_like: artist.soundalike_name || "—",
  };

  state.tray.push(trayItem);
  saveTrayToStorage();
  drawTray();

  if (!trayItem.sounds_like || trayItem.sounds_like === "—") {
    try {
      const topFans = await getFans(artist.artist_id, 1);
      trayItem.sounds_like = topFans[0]?.name ?? "—";
      saveTrayToStorage();
      drawTray();
    } catch (e) {}
  }
}

function removeFromTray(artistId) {
  state.tray = state.tray.filter((item) => item.artist.artist_id !== artistId);
  saveTrayToStorage();
  drawTray();
}

function clearTray() {
  state.tray = [];
  saveTrayToStorage();
  drawTray();
}

function drawTray() {
  const count = state.tray.length;
  $("tray-count").textContent = `${count} act${count === 1 ? "" : "s"} queued`;
  $("export").disabled = count === 0;

  if (count === 0) {
    $("tray-body").innerHTML =
      '<span style="font-size:12px; color:var(--text-tertiary); padding-left:4px;">No acts queued. Click "+ Add to Shortlist" on any artist card.</span>';
    return;
  }

  $("tray-body").innerHTML = state.tray
    .map(
      (item) => `
    <div class="tray-chip">
      <span><b>${esc(item.artist.name)}</b> (${pct(item.artist.growth)})</span>
      <button type="button" class="tray-chip-remove" data-remove="${item.artist.artist_id}" title="Remove">✕</button>
    </div>`
    )
    .join("");
}

// Formula injection protection for CSV export
const csvCell = (v, isText = false) => {
  if (v == null) return "";
  let s = String(v);
  if (isText && /^[=+\-@\t\r]/.test(s)) {
    s = "'" + s;
  }
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

function exportCsv() {
  if (state.tray.length === 0) return;

  const headers = [
    "artist_mbid",
    "name",
    "market_country",
    "first_catalogued_date",
    "baseline_listeners_mo",
    "recent_listeners_mo",
    "net_listeners_gain",
    "growth_percent",
    "growth_ratio",
    "top_benchmark_overlap",
  ];

  const rows = state.tray.map((t) => {
    const a = t.artist;
    return [
      csvCell(a.artist_mbid),
      csvCell(a.name, true),
      csvCell(a.country, true),
      csvCell(a.first_release_date),
      csvCell(f1(a.baseline)),
      csvCell(f1(a.recent)),
      csvCell(Math.round(a.net_listeners || 0)),
      csvCell(pct(a.growth), true),
      csvCell(Number(a.growth || 0).toFixed(4)),
      csvCell(t.sounds_like, true),
    ].join(",");
  });

  const csvContent = [headers.join(","), ...rows].join("\n") + "\n";
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", `echoai_shortlist_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// ---- Global Event Delegations ----
document.addEventListener("click", (e) => {
  const t = e.target;

  // Catalog Scope Toggles (Emerging vs All)
  if (t.closest("#btn-scope-emerging")) {
    state.scope = "emerging";
    state.filters.status = "emerging";
    $("f-status").value = "emerging";
    $("btn-scope-emerging").classList.add("active");
    $("btn-scope-all").classList.remove("active");
    $("scope-description").textContent = "Showing qualifying emerging acts meeting 90th percentile growth and size criteria.";
    state.page = 0;
    loadList();
    return;
  }

  if (t.closest("#btn-scope-all")) {
    state.scope = "all";
    state.filters.status = "";
    $("f-status").value = "";
    $("btn-scope-all").classList.add("active");
    $("btn-scope-emerging").classList.remove("active");
    $("scope-description").textContent = "Showing all 58 artists in catalog to benchmark emerging acts against established talent.";
    state.page = 0;
    loadList();
    return;
  }

  // View switchers
  if (t.closest("#btn-view-cards")) {
    state.viewMode = "cards";
    $("btn-view-cards").classList.add("active");
    $("btn-view-table").classList.remove("active");
    drawList();
    return;
  }
  if (t.closest("#btn-view-table")) {
    state.viewMode = "table";
    $("btn-view-table").classList.add("active");
    $("btn-view-cards").classList.remove("active");
    drawList();
    return;
  }

  // Chart Mode Toggles
  if (t.closest("#btn-chart-scatter")) {
    state.chartMode = "scatter";
    $("btn-chart-scatter").classList.add("active");
    $("btn-chart-trajectories").classList.remove("active");
    $("chart-heading").textContent = "Audience Scale vs. Growth Velocity Map";
    $("chart-sub").textContent = "Visualizing artists along monthly listener scale (X) and 6-month growth velocity (Y)";
    drawMainChart();
    return;
  }
  if (t.closest("#btn-chart-trajectories")) {
    state.chartMode = "trajectories";
    $("btn-chart-trajectories").classList.add("active");
    $("btn-chart-scatter").classList.remove("active");
    $("chart-heading").textContent = "6-Month Growth Trajectory Comparison";
    $("chart-sub").textContent = "Tracking monthly distinct listener growth from March to August 2026 across acts";
    drawMainChart();
    return;
  }

  // Data & Cleaning Modal
  if (t.closest("#btn-open-cleaning")) {
    $("modal-cleaning").style.display = "flex";
    return;
  }
  if (t.closest("#btn-close-cleaning") || t.id === "modal-cleaning") {
    $("modal-cleaning").style.display = "none";
    return;
  }

  // Pager
  if (t.dataset.page) {
    state.page += +t.dataset.page;
    if (state.viewMode === "cards") drawCards();
    else drawTable();
    return;
  }

  // Add from Card (Direct & Robust Event Target)
  const cardAddBtn = t.closest("[data-card-add]");
  if (cardAddBtn) {
    const id = +cardAddBtn.dataset.cardAdd;
    const artist = state.rows.find((r) => r.artist_id === id);
    if (artist) {
      addToTray(artist);
      cardAddBtn.textContent = "✓ Added";
      cardAddBtn.classList.add("added");
      setTimeout(() => {
        cardAddBtn.textContent = "+ Add to Shortlist";
        cardAddBtn.classList.remove("added");
      }, 1500);
    }
    return;
  }

  // Add from Spotlight
  if (t.closest("#btn-add-detail")) {
    if (detailArtist) {
      addToTray(detailArtist);
      const b = $("btn-add-detail");
      b.textContent = "✓ Added to Shortlist";
      setTimeout(() => {
        b.textContent = "+ Add to Playlist Shortlist";
      }, 1500);
    }
    return;
  }

  // Remove from Tray
  const removeBtn = t.closest("[data-remove]");
  if (removeBtn) {
    removeFromTray(+removeBtn.dataset.remove);
    return;
  }

  // Select Card
  const card = t.closest(".artist-card");
  if (card && !t.closest(".card-actions-row")) {
    selectArtist(+card.dataset.id);
    return;
  }

  // Select Table Row
  const tr = t.closest("#table tbody tr");
  if (tr && !t.closest("button")) {
    selectArtist(+tr.dataset.id);
  }
});

// ---- Initialization ----
async function init() {
  // Theme initialization
  const savedTheme = localStorage.getItem("echoai_curator_theme") || "theme-light";
  document.documentElement.dataset.theme = savedTheme;
  $("theme-selector").value = savedTheme;
  $("theme-selector").addEventListener("change", (e) => {
    const chosen = e.target.value;
    document.documentElement.dataset.theme = chosen;
    localStorage.setItem("echoai_curator_theme", chosen);
    drawMainChart();
    if (state.selectedId) loadSpotlight(state.selectedId);
  });

  loadTrayFromStorage();
  drawTray();

  const opt = await getOptions();

  // Genre Dropdown
  $("f-genre").innerHTML =
    '<option value="">All Genres</option>' +
    opt.genres.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join("");

  // Country Dropdown
  $("f-country").innerHTML =
    '<option value="">All Markets</option>' +
    opt.countries.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");

  syncFilterInputs();

  // Filter change listeners
  ["f-search", "f-status", "f-genre", "f-country", "f-tier", "f-sort"].forEach((id) => {
    $(id).addEventListener("input", onFilterChange);
    $(id).addEventListener("change", onFilterChange);
  });

  $("f-reset").addEventListener("click", () => {
    state.scope = "emerging";
    state.filters = {
      search: "",
      status: "",
      genre: "",
      country: "",
      size_tier: "",
      sort_by: "growth_desc",
    };
    $("btn-scope-emerging").classList.add("active");
    $("btn-scope-all").classList.remove("active");
    syncFilterInputs();
    state.page = 0;
    loadList();
  });

  $("export").addEventListener("click", exportCsv);
  $("tray-clear").addEventListener("click", clearTray);

  await loadList();
}

init().catch((err) => {
  console.error("Init failed:", err);
  $("list-msg").style.display = "block";
  $("list-msg").innerHTML = '<div style="color:var(--text-secondary);">Failed to connect to Discovery server.</div>';
});
