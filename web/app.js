import { getOptions, getShortlist, getArtist, getTrend, getFans, getTracks } from "./api.js";
import {
  renderScatter,
  renderMultiTrend,
  renderTrend,
  renderFans,
  generateSparklineSvg,
  setChartZoom,
} from "./charts.js";

// ---- Single App State ----
const state = {
  stage: "launchpad", // 'launchpad' | 'dashboard'
  filters: {
    search: "",
    status: "",
    genre: "",
    country: "",
    size_tier: "",
    sort_by: "growth_desc",
  },
  sliders: {
    min_release: "2023-01-01",
    growth_pct: 0.90,
    size_pct: 0.90,
    min_baseline: 5,
  },
  defaults: {},
  viewMode: "cards", // 'cards' | 'table'
  chartMode: "scatter", // 'scatter' | 'trajectories'
  zoomMode: "auto", // 'auto' | 'emerging' | 'superstars' | 'velocity'
  scope: "emerging", // 'emerging' | 'all'
  activeMission: "🌟 The Official Emerging Shortlist",
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
const pct = (x) => (x == null || isNaN(x) ? "+0%" : `+${Math.round(x * 100)}%`);

// Table Column Definitions
const COLS = [
  ["name", "Artist", false],
  ["status", "Category", false],
  ["country", "Market", false],
  ["top_genres", "Genre", false],
  ["trend", "6M Trend", false],
  ["baseline", "Mar '26", true],
  ["recent", "Aug '26", true],
  ["growth", "Growth", true],
  ["soundalike_name", "Audience Overlap", false],
];

// ---- Stage Switching (Curator User Flow) ----
function switchStage(stageName) {
  state.stage = stageName;
  const launchpad = $("stage-launchpad");
  const dashboard = $("stage-dashboard");

  if (stageName === "dashboard") {
    if (launchpad) {
      launchpad.hidden = true;
      launchpad.style.display = "none";
    }
    if (dashboard) {
      dashboard.hidden = false;
      dashboard.style.display = "block";
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (state.rows.length === 0) {
      loadList();
    } else {
      drawList();
    }
  } else {
    if (dashboard) {
      dashboard.hidden = true;
      dashboard.style.display = "none";
    }
    if (launchpad) {
      launchpad.hidden = false;
      launchpad.style.display = "block";
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

// ---- Storage: Shortlist Tray ----
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
  const s = state.sliders;
  const q = {
    min_release: s.min_release || "2023-01-01",
    min_baseline: s.min_baseline != null ? s.min_baseline : 5,
    size_pct: s.size_pct != null ? s.size_pct : 0.90,
    growth_pct: s.growth_pct != null ? s.growth_pct : 0.90,
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
  if ($("f-search")) $("f-search").value = f.search || "";
  if ($("f-status")) $("f-status").value = f.status || "";
  if ($("f-genre")) $("f-genre").value = f.genre || "";
  if ($("f-country")) $("f-country").value = f.country || "";
  if ($("f-tier")) $("f-tier").value = f.size_tier || "";
  if ($("f-sort")) $("f-sort").value = f.sort_by || "growth_desc";
}

function syncSliderInputs() {
  const s = state.sliders;
  if ($("slider-release-year") && s.min_release) {
    const yr = s.min_release.split("-")[0];
    $("slider-release-year").value = yr;
    $("val-release-year").textContent = `Debuted ≥ Jan 1, ${yr}`;
  }
  if ($("slider-growth-pct") && s.growth_pct != null) {
    const pctVal = Math.round(s.growth_pct * 100);
    $("slider-growth-pct").value = pctVal;
    const note = pctVal >= 95 ? " (Ultra-Breakout)" : pctVal === 90 ? " (Strict Default)" : "";
    $("val-growth-pct").textContent = `≥ ${pctVal}th Pct${note}`;
  }
  if ($("slider-size-pct") && s.size_pct != null) {
    const pctVal = Math.round(s.size_pct * 100);
    $("slider-size-pct").value = pctVal;
    $("val-size-pct").textContent = `≤ ${pctVal}th Pct Size`;
  }
  if ($("slider-baseline") && s.min_baseline != null) {
    $("slider-baseline").value = s.min_baseline;
    $("val-baseline").textContent = `≥ ${s.min_baseline} Listeners`;
  }
}

function readFilterInputs() {
  state.filters = {
    search: $("f-search") ? $("f-search").value.trim() : "",
    status: $("f-status") ? $("f-status").value || "" : "",
    genre: $("f-genre") ? $("f-genre").value || "" : "",
    country: $("f-country") ? $("f-country").value || "" : "",
    size_tier: $("f-tier") ? $("f-tier").value || "" : "",
    sort_by: $("f-sort") ? $("f-sort").value || "growth_desc" : "growth_desc",
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
  $("list-msg").innerHTML = "<div>Scanning database…</div>";

  try {
    const res = await getShortlist(buildQuery());
    if (seq !== listSeq) return;

    state.rows = res.artists;
    state.thresholds = res.thresholds;

    const count = state.rows.length;
    $("kpi-count").textContent = count.toLocaleString();
    $("kpi-size").textContent = `≤ ${f1(res.thresholds.recent_cutoff)} /mo`;
    $("kpi-growth").textContent = `≥ ${pct(res.thresholds.growth_cutoff)}`;

    // Update dynamic KPI labels to reflect slider values
    const growthPctVal = Math.round((state.sliders.growth_pct || 0.90) * 100);
    const sizePctVal = Math.round((state.sliders.size_pct || 0.90) * 100);
    if ($("kpi-growth-label")) $("kpi-growth-label").textContent = `Min Growth Rate (${growthPctVal}th %)`;
    if ($("kpi-size-label")) $("kpi-size-label").textContent = `Audience Limit (${sizePctVal}th %)`;

    // Dynamic Scope Badges & Descriptions
    if (state.scope === "emerging") {
      if ($("scope-count-emerging")) $("scope-count-emerging").textContent = count;
      if ($("active-mission-pill")) {
        $("active-mission-pill").textContent = `Curator Studio: 🌟 Emerging Shortlist (${count} Act${count === 1 ? "" : "s"})`;
      }
      if ($("scope-description")) {
        const yr = (state.sliders.min_release || "2023-01-01").split("-")[0];
        $("scope-description").textContent =
          `Showing ${count} qualifying emerging act${count === 1 ? "" : "s"} passing the ${growthPctVal}th percentile growth gate (≥ ${pct(res.thresholds.growth_cutoff)}), ${sizePctVal}th percentile audience limit (≤ ${f1(res.thresholds.recent_cutoff)}/mo), and debuted on or after ${yr}.`;
      }
    } else {
      if ($("scope-count-all")) $("scope-count-all").textContent = count;
      if ($("active-mission-pill")) {
        $("active-mission-pill").textContent = `Curator Studio: 🌐 Catalog Explorer (${count} Acts)`;
      }
      if ($("scope-description")) {
        $("scope-description").textContent =
          `Showing all ${count} catalog artists. Benchmarking emerging acts against mainstream talent.`;
      }
    }

    // Top anchor
    const topSound = state.rows.find((r) => r.soundalike_name)?.soundalike_name || "BTS";
    $("kpi-anchor").textContent = `${topSound} (89%)`;

    // Dynamic Heading
    if (state.filters.search) {
      $("results-heading").textContent = `Search Results: "${esc(state.filters.search)}"`;
      $("kpi-count-label").textContent = "Artists Found";
    } else if (state.filters.status === "emerging" || state.scope === "emerging") {
      $("results-heading").textContent = `Qualifying Emerging Artists (${count} Acts at ${growthPctVal}th % Growth)`;
      $("kpi-count-label").textContent = "Qualifying Emerging Acts";
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
    $("table-view").style.display = "none";
    $("list-msg").style.display = "block";
    $("list-msg").innerHTML = `
      <div style="color:var(--text-secondary);">
        Failed to fetch artists. Please ensure backend is running.
        <br><button type="button" id="btn-retry-list" class="btn-secondary" style="margin-top:10px;">Retry</button>
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
    $("cards-view").style.display = "none";
    $("cards-view").hidden = true;
    $("table-view").hidden = true;
    $("table-view").style.display = "none";
    $("list-msg").innerHTML = `
      <div style="padding: 24px; color:var(--text-secondary);">
        <b>No artists matched your filter criteria.</b><br>
        Try loosening threshold sliders, clearing search keywords, or clicking <b>"Reset"</b>.
      </div>`;
    $("results-counter").textContent = "0 artists found";
    drawMainChart();
    return;
  }

  $("results-counter").textContent = `Showing ${total} artist${total === 1 ? "" : "s"}`;

  drawMainChart();

  // Robust View Switching
  if (state.viewMode === "cards") {
    $("btn-view-cards").classList.add("active");
    $("btn-view-table").classList.remove("active");
    $("cards-view").hidden = false;
    $("cards-view").style.display = "grid";
    $("table-view").hidden = true;
    $("table-view").style.display = "none";
    drawCards();
  } else {
    $("btn-view-table").classList.add("active");
    $("btn-view-cards").classList.remove("active");
    $("cards-view").hidden = true;
    $("cards-view").style.display = "none";
    $("table-view").hidden = false;
    $("table-view").style.display = "block";
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
  if (state.stage !== "dashboard") return;
  const canvas = $("scatter");
  if (!canvas) return;

  if (state.chartMode === "scatter") {
    mainChart = renderScatter(
      canvas,
      state.rows,
      state.thresholds,
      state.selectedId,
      selectArtist,
      mainChart,
      state.zoomMode
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
      const sparkSvg = generateSparklineSvg(getSparklineValues(a), 110, 24);
      const isSelected = a.artist_id === state.selectedId;

      const soundText = a.soundalike_name
        ? `<div class="card-soundalike">Fans also listen to: <b>${esc(a.soundalike_name)}</b> (${Math.round((a.soundalike_share || 0) * 100)}%)</div>`
        : "";

      const statusPill = a.is_emerging
        ? '<span class="status-pill emerging">🌟 Emerging Act</span>'
        : a.artist_status === "established"
        ? '<span class="status-pill established">👑 Benchmark</span>'
        : '<span class="status-pill candidate">Candidate</span>';

      return `
      <div class="artist-card ${isSelected ? "selected" : ""}" data-id="${a.artist_id}">
        <div>
          <div class="card-top-row">
            <span class="card-artist-name">${esc(a.name)}</span>
            ${statusPill}
          </div>
          <div class="card-genre-row">
            ${unk(a.top_genres)} · ${unk(a.country)}
          </div>

          <div class="card-metrics-grid">
            <div class="card-metric-cell">
              <span class="card-metric-label">Mar '26</span>
              <span class="card-metric-val">${f1(a.baseline)}</span>
            </div>
            <div class="card-metric-cell">
              <span class="card-metric-label">Aug '26</span>
              <span class="card-metric-val">${f1(a.recent)}</span>
            </div>
            <div class="card-metric-cell">
              <span class="card-metric-label">6M Growth</span>
              <span class="card-metric-val growth-highlight">${pct(a.growth)}</span>
            </div>
          </div>

          <div style="margin: 12px 0 6px 0;">
            <span style="font-size:11px; color:var(--text-tertiary); display:block; margin-bottom:4px;">Monthly Trajectory</span>
            ${sparkSvg}
          </div>

          ${soundText}
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
  if (state.stage === "dashboard") {
    loadSpotlight(artistId);
  }

  // Update floating chart inspector
  const artist = state.rows.find((r) => r.artist_id === artistId);
  if (artist && $("chart-inspector")) {
    $("chart-inspector").style.display = "flex";
    $("ins-name").textContent = artist.name;
    const statusText = artist.is_emerging
      ? "🌟 Emerging"
      : artist.artist_status === "established"
      ? "👑 Benchmark"
      : "Candidate";
    $("ins-meta").textContent = `${statusText} · ${unk(artist.top_genres)} · ${unk(artist.country)} · Recent: ${Math.round(artist.recent)}/mo · Growth: +${Math.round((artist.growth || 0) * 100)}%`;
    $("btn-ins-add").dataset.cardAdd = artist.artist_id;
  }
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
  $("d-narrative").innerHTML = "Analyzing telemetry…";
  $("d-badge").innerHTML = "";

  try {
    const [artist, trendData, fansData, tracksData] = await Promise.all([
      getArtist(artistId),
      getTrend(artistId),
      getFans(artistId, 5),
      getTracks(artistId, 5),
    ]);

    detailArtist = artist;

    $("d-name").textContent = artist.name;
    $("d-avatar").textContent = (artist.name || "A").slice(0, 1).toUpperCase();

    const relDate = artist.first_release_date ? artist.first_release_date.slice(0, 10) : "Unknown";
    $("d-meta").textContent = `${unk(artist.artist_type)} · ${unk(artist.country)} · Debuted: ${relDate}`;

    // Status Badge
    if (artist.is_emerging) {
      $("d-badge").innerHTML = '<span class="status-pill emerging">🌟 Verified Emerging Act (90th Pct Growth)</span>';
    } else if (artist.artist_status === "established") {
      $("d-badge").innerHTML = '<span class="status-pill established">👑 Mainstream Benchmark Act</span>';
    } else {
      $("d-badge").innerHTML = '<span class="status-pill candidate">Developing Talent Candidate</span>';
    }

    // Editorial narrative
    const pctG = Math.round((artist.growth || 0) * 100);
    const soundMsg = artist.soundalike_name
      ? `Their audience heavily overlaps with listeners of <b>${esc(artist.soundalike_name)}</b>.`
      : "";

    $("d-narrative").innerHTML = `
      <b>${esc(artist.name)}</b> grew their listener base by <b>+${pctG}%</b> between March and August 2026, scaling from <b>${f1(artist.baseline)}</b> to <b>${f1(artist.recent)}</b> distinct monthly scrobblers. ${soundMsg}
    `;

    // 6-Month Trajectory Chart
    trendChart = renderTrend($("trend"), trendData, trendChart);

    // Fans Also Listen To
    renderFans($("d-fans"), fansData);

    // Top Songs
    $("d-tracks").innerHTML =
      tracksData.length === 0
        ? '<div style="color:var(--text-secondary); font-size:12px;">No top recording data available.</div>'
        : tracksData
            .map(
              (t, i) => `
          <div class="top-track-row">
            <span class="track-rank">${i + 1}</span>
            <div class="track-title-cell">
              <span class="track-name">${esc(t.recording_title)}</span>
              <span class="track-growth-tag">+${Math.round((t.track_growth || 0) * 100)}% spike</span>
            </div>
          </div>
        `
            )
            .join("");
  } catch (err) {
    console.error("Failed to load spotlight:", err);
    $("d-name").textContent = "Unable to load artist profile";
  }
}

// ---- Shortlist Tray Actions ----
function addToTray(artist) {
  if (!state.tray.some((x) => x.artist_id === artist.artist_id)) {
    state.tray.push(artist);
    saveTrayToStorage();
    drawTray();
  }
}

function removeFromTray(artistId) {
  state.tray = state.tray.filter((x) => x.artist_id !== artistId);
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
  $("tray-count").textContent = `${count} act${count === 1 ? "" : "s"} shortlisted`;
  $("export").disabled = count === 0;

  if (count === 0) {
    $("tray-body").innerHTML = '<span style="color:var(--text-tertiary); font-size:12px;">No acts shortlisted yet. Click "+ Add" on any artist card.</span>';
    return;
  }

  $("tray-body").innerHTML = state.tray
    .map(
      (a) => `
      <div class="tray-chip">
        <span>${esc(a.name)}</span>
        <button type="button" class="tray-chip-remove" data-remove="${a.artist_id}">×</button>
      </div>
    `
    )
    .join("");
}

function exportCsv() {
  if (state.tray.length === 0) return;
  const headers = ["Artist ID", "Name", "Country", "Genres", "Baseline (Mar '26)", "Recent (Aug '26)", "Growth %", "Overlap Benchmark"];
  const rows = state.tray.map((a) => [
    a.artist_id,
    `"${(a.name || "").replace(/"/g, '""')}"`,
    `"${a.country || "Unknown"}"`,
    `"${(a.top_genres || "").replace(/"/g, '""')}"`,
    f1(a.baseline),
    f1(a.recent),
    pct(a.growth),
    `"${(a.soundalike_name || "").replace(/"/g, '""')}"`,
  ]);

  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
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

  // Curator Portals Click (Stage 1 -> Stage 2 Transition)
  const portal = t.closest(".portal-card[data-mission]");
  if (portal) {
    const mission = portal.dataset.mission;
    if (mission === "rockets") {
      state.scope = "emerging";
      state.filters.status = "emerging";
      state.filters.sort_by = "growth_desc";
      state.sliders.growth_pct = 0.90;
      state.activeMission = "🚀 Breakout Rockets (Fastest Growth)";
    } else if (mission === "emerging") {
      state.scope = "emerging";
      state.filters.status = "emerging";
      state.filters.sort_by = "growth_desc";
      state.activeMission = "🌟 The Official Emerging Shortlist";
    } else if (mission === "global") {
      state.scope = "all";
      state.filters.status = "";
      state.filters.country = "GB";
      state.filters.sort_by = "growth_desc";
      state.activeMission = "🌍 Global Underground (International)";
    } else if (mission === "all") {
      state.scope = "all";
      state.filters.status = "";
      state.filters.sort_by = "listeners_desc";
      state.activeMission = "🌐 Catalog & Benchmark Explorer (All 58 Acts)";
    }

    if ($("active-mission-pill")) {
      $("active-mission-pill").textContent = `Curator Studio: ${state.activeMission}`;
    }

    $("btn-scope-emerging").classList.toggle("active", state.scope === "emerging");
    $("btn-scope-all").classList.toggle("active", state.scope === "all");
    syncFilterInputs();
    syncSliderInputs();
    switchStage("dashboard");
    loadList();
    return;
  }

  // Enter Studio Button
  if (t.closest("#btn-enter-studio") || t.closest(".btn-hero-primary")) {
    switchStage("dashboard");
    return;
  }

  // Return to Hub Button
  if (t.closest("#btn-back-hub")) {
    switchStage("launchpad");
    return;
  }

  // Quick Preview Card click
  const previewCard = t.closest(".preview-act-card[data-preview-artist]");
  if (previewCard) {
    const artistId = +previewCard.dataset.previewArtist;
    switchStage("dashboard");
    selectArtist(artistId);
    return;
  }

  // Quick studio jump tabs
  if (t.closest("#tab-jump-chart")) {
    $("section-visualizer")?.scrollIntoView({ behavior: "smooth" });
    return;
  }
  if (t.closest("#tab-jump-sliders")) {
    const panel = $("tuning-content");
    if (panel) panel.style.display = "grid";
    $("tuning-panel")?.scrollIntoView({ behavior: "smooth" });
    return;
  }
  if (t.closest("#tab-jump-results")) {
    $("main-workspace")?.scrollIntoView({ behavior: "smooth" });
    return;
  }

  // Tuning Panel Collapse/Expand
  if (t.closest("#tuning-toggle-btn")) {
    const content = $("tuning-content");
    const icon = $("tuning-toggle-icon");
    if (content) {
      const isHidden = content.style.display === "none";
      content.style.display = isHidden ? "grid" : "none";
      if (icon) icon.textContent = isHidden ? "▼ Click to Collapse" : "▶ Click to Expand";
    }
    return;
  }

  // Interactive Chart Zoom Buttons
  const zoomBtn = t.closest(".zoom-btn[data-zoom]");
  if (zoomBtn) {
    const mode = zoomBtn.dataset.zoom;
    state.zoomMode = mode;
    document.querySelectorAll(".zoom-btn").forEach((b) => b.classList.remove("active"));
    zoomBtn.classList.add("active");
    if (mainChart) {
      setChartZoom(mainChart, mode);
    }
    return;
  }

  // Chart Inspector Spotlight action
  if (t.closest("#btn-ins-spotlight")) {
    $("spotlight-column")?.scrollIntoView({ behavior: "smooth" });
    return;
  }

  // Catalog Scope Toggles (Emerging vs All)
  if (t.closest("#btn-scope-emerging")) {
    state.scope = "emerging";
    state.filters.status = "emerging";
    $("f-status").value = "emerging";
    $("btn-scope-emerging").classList.add("active");
    $("btn-scope-all").classList.remove("active");
    $("scope-description").textContent = "Showing qualifying emerging acts meeting 90th percentile growth and audience criteria.";
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

  // Working View switchers
  if (t.closest("#btn-view-cards")) {
    state.viewMode = "cards";
    $("btn-view-cards").classList.add("active");
    $("btn-view-table").classList.remove("active");
    $("cards-view").hidden = false;
    $("cards-view").style.display = "grid";
    $("table-view").hidden = true;
    $("table-view").style.display = "none";
    drawCards();
    return;
  }
  if (t.closest("#btn-view-table")) {
    state.viewMode = "table";
    $("btn-view-table").classList.add("active");
    $("btn-view-cards").classList.remove("active");
    $("cards-view").hidden = true;
    $("cards-view").style.display = "none";
    $("table-view").hidden = false;
    $("table-view").style.display = "block";
    drawTable();
    return;
  }

  // Chart Mode Toggles
  if (t.closest("#btn-chart-scatter")) {
    state.chartMode = "scatter";
    $("btn-chart-scatter").classList.add("active");
    $("btn-chart-trajectories").classList.remove("active");
    $("chart-heading").textContent = "Audience Scale vs. Growth Velocity Map";
    $("chart-sub").textContent = "Visualizing artists along monthly listener scale (X) and 6-month growth velocity (Y). Click any dot to inspect.";
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
  if (t.closest("#btn-open-cleaning") || t.closest("#btn-launch-cleaning")) {
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
  syncSliderInputs();

  // Filter change listeners
  ["f-search", "f-status", "f-genre", "f-country", "f-tier", "f-sort"].forEach((id) => {
    $(id).addEventListener("input", onFilterChange);
    $(id).addEventListener("change", onFilterChange);
  });

  // Slider change listeners
  if ($("slider-release-year")) {
    $("slider-release-year").addEventListener("input", (e) => {
      const yr = e.target.value;
      state.sliders.min_release = `${yr}-01-01`;
      $("val-release-year").textContent = `Debuted ≥ Jan 1, ${yr}`;
      onFilterChange();
    });
  }

  if ($("slider-growth-pct")) {
    $("slider-growth-pct").addEventListener("input", (e) => {
      const val = +e.target.value;
      state.sliders.growth_pct = val / 100;
      const note = val >= 95 ? " (Ultra-Breakout)" : val === 90 ? " (Strict Default)" : " (Broader Pool)";
      $("val-growth-pct").textContent = `≥ ${val}th Pct${note}`;
      if ($("kpi-growth-label")) $("kpi-growth-label").textContent = `Min Growth Rate (${val}th %)`;
      onFilterChange();
    });
  }

  if ($("slider-size-pct")) {
    $("slider-size-pct").addEventListener("input", (e) => {
      const val = +e.target.value;
      state.sliders.size_pct = val / 100;
      const note = val <= 75 ? " (Micro Only)" : val === 90 ? " (Default Ceiling)" : "";
      $("val-size-pct").textContent = `≤ ${val}th Pct Size${note}`;
      if ($("kpi-size-label")) $("kpi-size-label").textContent = `Audience Limit (${val}th %)`;
      onFilterChange();
    });
  }

  if ($("slider-baseline")) {
    $("slider-baseline").addEventListener("input", (e) => {
      const val = +e.target.value;
      state.sliders.min_baseline = val;
      $("val-baseline").textContent = `≥ ${val} Listeners`;
      onFilterChange();
    });
  }

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
    state.sliders = {
      min_release: "2023-01-01",
      growth_pct: 0.90,
      size_pct: 0.90,
      min_baseline: 5,
    };
    $("btn-scope-emerging").classList.add("active");
    $("btn-scope-all").classList.remove("active");
    syncFilterInputs();
    syncSliderInputs();
    state.page = 0;
    loadList();
  });

  $("export").addEventListener("click", exportCsv);
  $("tray-clear").addEventListener("click", clearTray);

  // Initial load: keep on launchpad stage by default, but populate list in background
  await loadList();
}

init().catch((err) => {
  console.error("Init failed:", err);
  $("list-msg").style.display = "block";
  $("list-msg").innerHTML = '<div style="color:var(--text-secondary);">Failed to connect to Discovery server.</div>';
});