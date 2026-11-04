// Visual Rendering Engine (EchoAI — DSO 576)
// Drawing only: no fetch calls, no state mutations.

const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

export function getThemeAccent() {
  if (typeof window === "undefined") return "#f59e0b";
  return getComputedStyle(document.documentElement).getPropertyValue("--accent-primary").trim() || "#f59e0b";
}

/**
 * Generates an ultra-clean, zero-overhead inline SVG sparkline curve.
 * Used inside artist cards and table rows without Chart.js overhead.
 */
export function generateSparklineSvg(data = [], width = 100, height = 28) {
  if (!data || data.length < 2) return "";
  const values = data.map((v) => Number(v) || 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = 3;

  const points = values.map((val, idx) => {
    const x = padding + (idx / (values.length - 1)) * (width - 2 * padding);
    const y = height - padding - ((val - min) / range) * (height - 2 * padding);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polyline = points.join(" ");
  const lastPoint = points[points.length - 1].split(",");
  const strokeColor = getThemeAccent();

  return `
    <svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block;">
      <polyline
        fill="none"
        stroke="${strokeColor}"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        points="${polyline}"
      />
      <circle cx="${lastPoint[0]}" cy="${lastPoint[1]}" r="3" fill="${strokeColor}" />
    </svg>
  `;
}

/**
 * Artist Name Annotation Plugin for Chart.js.
 * Renders legible artist name pills directly next to each scatter dot.
 */
const artistScatterLabelsPlugin = {
  id: "artistScatterLabels",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    const accent = getThemeAccent();
    ctx.save();
    ctx.font = "600 11px Inter, sans-serif";
    ctx.textBaseline = "middle";

    chart.data.datasets.forEach((dataset, datasetIndex) => {
      if (dataset.type === "line" || !dataset.data) return;
      const meta = chart.getDatasetMeta(datasetIndex);
      if (meta.hidden) return;

      meta.data.forEach((element, index) => {
        const item = dataset.data[index];
        if (!item || !item.r) return;

        // In dense datasets, only label emerging acts, established anchors, or selected item
        const r = item.r;
        const isSelected = item.isSelected;
        const shouldLabel = isSelected || r.is_emerging || (r.recent && r.recent > 300) || chart.data.datasets[0].data.length <= 12;
        if (!shouldLabel) return;

        const { x, y } = element;
        const nameText = r.recent > 300
          ? `👑 ${r.name} (${Math.round(r.recent)}/mo)`
          : `${r.name} (+${Math.round((r.growth || 0) * 100)}%)`;

        const textWidth = ctx.measureText(nameText).width;
        const pillWidth = textWidth + 12;
        const pillHeight = 20;
        const pillX = Math.min(chart.chartArea.right - pillWidth - 4, x + 8);
        const pillY = Math.max(chart.chartArea.top + 4, y - 10);

        ctx.fillStyle = isSelected ? "rgba(245, 158, 11, 0.25)" : "rgba(24, 28, 38, 0.88)";
        ctx.strokeStyle = isSelected ? accent : "rgba(255, 255, 255, 0.16)";
        ctx.lineWidth = 1;

        ctx.beginPath();
        ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 4);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isSelected ? accent : "#f8fafc";
        ctx.fillText(nameText, pillX + 6, pillY + pillHeight / 2);
      });
    });

    ctx.restore();
  },
};

/**
 * Renders the primary Growth vs. Audience Distribution Scatter Plot.
 * Uses clean linear scales, direct canvas artist labels, and benchmark lines.
 */
export function renderScatter(
  canvas,
  rows = [],
  th = {},
  selectedId = null,
  onSelect = null,
  oldChart = null,
  zoomPreset = "auto"
) {
  if (oldChart) {
    oldChart.destroy();
  }

  if (!rows || rows.length === 0) {
    return null;
  }

  const accent = getThemeAccent();
  const xs = rows.map((r) => r.recent || 0);
  const ys = rows.map((r) => (r.growth || 0) * 100);

  const rawXmax = Math.max((th?.recent_cutoff || 100) * 1.15, Math.max(...xs) * 1.08, 100);
  const rawYmax = Math.max((th?.growth_cutoff ? th.growth_cutoff * 100 : 100) * 1.1, Math.max(...ys) * 1.08, 200);

  let scaleXMin = 0;
  let scaleXMax = Math.ceil(rawXmax / 50) * 50;
  let scaleYMin = 0;
  let scaleYMax = Math.ceil(rawYmax / 100) * 100;

  if (zoomPreset === "emerging") {
    scaleXMax = Math.min(scaleXMax, Math.max(350, Math.round((th?.recent_cutoff || 150) * 1.25)));
    scaleYMax = Math.min(scaleYMax, 1600);
  } else if (zoomPreset === "velocity") {
    scaleYMin = 400;
    scaleXMax = Math.min(scaleXMax, 400);
  } else if (zoomPreset === "superstars") {
    scaleXMin = 150;
    scaleYMax = Math.min(scaleYMax, 400);
  }

  // Background shaded target quadrant plugin
  const quadrantPlugin = {
    id: "quadrantShading",
    beforeDraw(chart) {
      const { ctx, chartArea, scales: { x, y } } = chart;
      if (!th || !th.recent_cutoff || th.growth_cutoff == null) return;

      const cutoffX = x.getPixelForValue(th.recent_cutoff);
      const cutoffY = y.getPixelForValue(th.growth_cutoff * 100);

      ctx.save();
      const qWidth = Math.max(0, Math.min(cutoffX, chartArea.right) - chartArea.left);
      const qHeight = Math.max(0, cutoffY - chartArea.top);

      ctx.fillStyle = "rgba(37, 99, 235, 0.05)";
      ctx.fillRect(chartArea.left, chartArea.top, qWidth, qHeight);

      ctx.restore();
    },
  };

  const pointsData = rows.map((r) => ({
    x: r.recent,
    y: (r.growth || 0) * 100,
    r,
    isSelected: r.artist_id === selectedId,
  }));

  const datasets = [
    {
      label: "Artists in View",
      type: "scatter",
      data: pointsData,
      backgroundColor: pointsData.map((d) => {
        if (d.isSelected) return accent;
        if (d.r.is_emerging) return accent;
        if (d.r.artist_status === "established") return "#38bdf8";
        return "rgba(148, 163, 184, 0.65)";
      }),
      borderColor: pointsData.map((d) => (d.isSelected ? "#ffffff" : "rgba(255, 255, 255, 0.3)")),
      borderWidth: pointsData.map((d) => (d.isSelected ? 3 : 1)),
      pointRadius: pointsData.map((d) => (d.isSelected ? 11 : d.r.is_emerging || d.r.recent > 300 ? 7 : 5)),
      pointHoverRadius: 13,
      pointHitRadius: 22,
    },
  ];

  // Add benchmark cutoff lines
  if (th?.recent_cutoff) {
    datasets.push({
      label: `Audience Limit (≤ ${Math.round(th.recent_cutoff)}/mo)`,
      type: "line",
      showLine: true,
      data: [
        { x: th.recent_cutoff, y: scaleYMin },
        { x: th.recent_cutoff, y: scaleYMax },
      ],
      borderColor: "rgba(217, 119, 6, 0.7)",
      borderDash: [5, 5],
      borderWidth: 1.5,
      pointRadius: 0,
      pointHitRadius: 0,
    });
  }

  if (th?.growth_cutoff != null) {
    const gVal = th.growth_cutoff * 100;
    datasets.push({
      label: `Min Growth (≥ +${Math.round(gVal)}%)`,
      type: "line",
      showLine: true,
      data: [
        { x: scaleXMin, y: gVal },
        { x: scaleXMax, y: gVal },
      ],
      borderColor: "rgba(217, 119, 6, 0.7)",
      borderDash: [5, 5],
      borderWidth: 1.5,
      pointRadius: 0,
      pointHitRadius: 0,
    });
  }

  const chart = new Chart(canvas, {
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      onHover: (event, chartElement) => {
        canvas.style.cursor = chartElement && chartElement.length ? "pointer" : "default";
      },
      scales: {
        x: {
          type: "linear",
          min: scaleXMin,
          max: scaleXMax,
          grid: { color: "rgba(148, 163, 184, 0.12)" },
          ticks: {
            color: "#64748b",
            font: { family: "Geist Mono, monospace", size: 11 },
          },
          title: {
            display: true,
            text: "Recent Monthly Listeners (Audience Scale)",
            color: "#475569",
            font: { size: 11, weight: "600" },
          },
        },
        y: {
          type: "linear",
          min: scaleYMin,
          max: scaleYMax,
          grid: { color: "rgba(148, 163, 184, 0.12)" },
          ticks: {
            color: "#64748b",
            font: { family: "Geist Mono, monospace", size: 11 },
            callback: (v) => `+${Math.round(v)}%`,
          },
          title: {
            display: true,
            text: "Listener Growth Velocity (%)",
            color: "#475569",
            font: { size: 11, weight: "600" },
          },
        },
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          align: "end",
          labels: {
            color: "#64748b",
            font: { size: 11 },
            boxWidth: 12,
            boxHeight: 2,
          },
        },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.94)",
          borderColor: "rgba(255, 255, 255, 0.15)",
          borderWidth: 1,
          padding: 12,
          titleColor: "#f8fafc",
          bodyColor: "#cbd5e1",
          cornerRadius: 8,
          callbacks: {
            title: (items) => items[0]?.raw?.r?.name || items[0]?.dataset?.label || "",
            label: (item) => {
              const r = item.raw.r;
              if (!r) return "";
              const status = r.is_emerging
                ? "🌟 Emerging Act"
                : r.artist_status === "established"
                ? "👑 Established Benchmark"
                : "Candidate Act";
              return [
                `Status: ${status}`,
                `Growth: +${Math.round((r.growth || 0) * 100)}% (Mar → Aug 2026)`,
                `Recent Audience: ${Math.round(r.recent)} listeners/mo (Baseline: ${Math.round(r.baseline)})`,
                r.soundalike_name
                  ? `Fans also like: ${r.soundalike_name} (${Math.round((r.soundalike_share || 0) * 100)}% match)`
                  : "",
                `Market: ${r.country || "Unknown"}`,
              ].filter(Boolean);
            },
          },
        },
      },
      onClick: (_evt, elements) => {
        if (!elements || elements.length === 0 || !onSelect) return;
        const el = elements[0];
        const dataset = datasets[el.datasetIndex];
        if (dataset && dataset.data && dataset.data[el.index]?.r) {
          onSelect(dataset.data[el.index].r.artist_id);
        }
      },
    },
    plugins: [quadrantPlugin, artistScatterLabelsPlugin],
  });

  chart._zoomPreset = zoomPreset;
  chart._th = th;
  chart._rawBounds = { scaleXMin, scaleXMax: rawXmax, scaleYMin, scaleYMax: rawYmax };
  return chart;
}

/**
 * Dynamically re-scales an existing Chart instance without destroying it.
 */
export function setChartZoom(chart, mode) {
  if (!chart || !chart.options || !chart.options.scales) return;
  const th = chart._th || {};
  const raw = chart._rawBounds || { scaleXMin: 0, scaleXMax: 400, scaleYMin: 0, scaleYMax: 1600 };

  if (mode === "emerging") {
    chart.options.scales.x.min = 0;
    chart.options.scales.x.max = Math.min(Math.ceil(raw.scaleXMax), Math.max(350, Math.round((th.recent_cutoff || 150) * 1.25)));
    chart.options.scales.y.min = 0;
    chart.options.scales.y.max = 1600;
  } else if (mode === "velocity") {
    chart.options.scales.x.min = 0;
    chart.options.scales.x.max = Math.min(Math.ceil(raw.scaleXMax), 400);
    chart.options.scales.y.min = 400;
    chart.options.scales.y.max = Math.ceil(raw.scaleYMax);
  } else if (mode === "superstars") {
    chart.options.scales.x.min = 150;
    chart.options.scales.x.max = Math.ceil(raw.scaleXMax);
    chart.options.scales.y.min = 0;
    chart.options.scales.y.max = 350;
  } else {
    // Auto / All
    chart.options.scales.x.min = 0;
    chart.options.scales.x.max = Math.ceil(raw.scaleXMax / 50) * 50;
    chart.options.scales.y.min = 0;
    chart.options.scales.y.max = Math.ceil(raw.scaleYMax / 100) * 100;
  }

  chart._zoomPreset = mode;
  chart.update();
}
}

/**
 * Comparative 6-Month Trajectory Plot.
 */
export function renderMultiTrend(canvas, rows = [], selectedId = null, onSelect = null, oldChart = null) {
  if (oldChart) {
    oldChart.destroy();
  }

  if (!rows || rows.length === 0) return null;

  const accent = getThemeAccent();
  const months = ["Mar", "Apr", "May", "Jun", "Jul", "Aug"];

  const zonesPlugin = {
    id: "trajectoryZones",
    beforeDraw(chart) {
      const { ctx, chartArea, scales: { x } } = chart;
      const mid = (x.getPixelForValue(2) + x.getPixelForValue(3)) / 2;
      ctx.save();
      ctx.fillStyle = "rgba(255, 255, 255, 0.02)";
      ctx.fillRect(chartArea.left, chartArea.top, mid - chartArea.left, chartArea.bottom - chartArea.top);
      ctx.fillStyle = "rgba(245, 158, 11, 0.04)";
      ctx.fillRect(mid, chartArea.top, chartArea.right - mid, chartArea.bottom - chartArea.top);

      ctx.font = "600 10px Geist Mono, monospace";
      ctx.fillStyle = "#525e70";
      ctx.fillText("BASELINE (MAR–MAY)", chartArea.left + 10, chartArea.top + 16);
      ctx.fillStyle = accent;
      ctx.fillText("RECENT (JUN–AUG)", mid + 10, chartArea.top + 16);
      ctx.restore();
    },
  };

  const topSubset = rows.slice(0, 10);
  const datasets = topSubset.map((a) => {
    const isSelected = a.artist_id === selectedId;
    const values = [
      a.listeners_2026_03 || 0,
      a.listeners_2026_04 || 0,
      a.listeners_2026_05 || 0,
      a.listeners_2026_06 || 0,
      a.listeners_2026_07 || 0,
      a.listeners_2026_08 || 0,
    ];

    let color = isSelected ? accent : a.is_emerging ? accent : "rgba(148, 163, 184, 0.5)";

    return {
      label: `${a.name} (+${Math.round((a.growth || 0) * 100)}%)`,
      data: values,
      borderColor: color,
      backgroundColor: isSelected ? "rgba(245, 158, 11, 0.15)" : "transparent",
      fill: isSelected,
      borderWidth: isSelected ? 3 : 1.5,
      pointRadius: isSelected ? 5 : 3,
      pointHoverRadius: 7,
      pointBackgroundColor: color,
      tension: 0.25,
      artist_id: a.artist_id,
    };
  });

  return new Chart(canvas, {
    type: "line",
    data: {
      labels: months,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8", font: { family: "Geist Mono, monospace", size: 11 } },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8", font: { family: "Geist Mono, monospace", size: 11 } },
          title: {
            display: true,
            text: "Distinct Monthly Listeners",
            color: "#a3a8b4",
            font: { size: 11, weight: "600" },
          },
        },
      },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: {
            color: "#94a3b8",
            font: { size: 11 },
            boxWidth: 12,
          },
        },
        tooltip: {
          backgroundColor: "#181c26",
          borderColor: "rgba(255, 255, 255, 0.15)",
          borderWidth: 1,
          padding: 10,
          titleColor: "#f8fafc",
          bodyColor: "#94a3b8",
        },
      },
      onClick: (_evt, elements) => {
        if (!elements || elements.length === 0 || !onSelect) return;
        const dsIndex = elements[0].datasetIndex;
        const artistId = datasets[dsIndex]?.artist_id;
        if (artistId) onSelect(artistId);
      },
    },
    plugins: [zonesPlugin],
  });
}

/**
 * Single Artist 6-Month Listener Trend Curve (Right Spotlight Panel).
 */
export function renderTrend(canvas, data = [], oldChart = null) {
  if (oldChart) {
    oldChart.destroy();
  }

  const accent = getThemeAccent();
  const label = (m) => ["Mar", "Apr", "May", "Jun", "Jul", "Aug"][(m % 100) - 3] || String(m);

  return new Chart(canvas, {
    type: "line",
    data: {
      labels: data.map((d) => label(d.month)),
      datasets: [
        {
          label: "Distinct Listeners",
          data: data.map((d) => d.listeners),
          borderColor: accent,
          backgroundColor: "rgba(245, 158, 11, 0.12)",
          fill: true,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: accent,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#94a3b8", font: { size: 10, family: "Geist Mono, monospace" } },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#94a3b8", font: { size: 10, family: "Geist Mono, monospace" } },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#181c26",
          borderColor: "rgba(255, 255, 255, 0.15)",
          borderWidth: 1,
          padding: 8,
          titleColor: "#f8fafc",
          bodyColor: "#94a3b8",
          callbacks: {
            label: (i) => `${i.parsed.y} listeners`,
          },
        },
      },
    },
  });
}

/**
 * Renders Taste Community Overlap Bars.
 */
export function renderFans(container, data = []) {
  if (!data || data.length === 0) {
    container.innerHTML = '<div class="overlap-item" style="color:var(--text-tertiary);">No established soundalike matches found.</div>';
    return;
  }

  const accent = getThemeAccent();
  container.innerHTML = data
    .slice(0, 5)
    .map((f) => {
      const sharePct = Math.round(f.share_of_fans * 100);
      return `
      <div class="overlap-item">
        <span class="overlap-item-name">${esc(f.name)}</span>
        <span class="overlap-item-share" style="color:${accent}; font-weight:700;">${sharePct}% shared fans</span>
      </div>
    `;
    })
    .join("");
}
