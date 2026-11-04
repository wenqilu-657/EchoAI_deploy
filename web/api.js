// API client for Emerging Artist Discovery (BUILD_SPEC.md v2.0)
// Pure fetch layer: returns parsed JSON or throws. Never touches the DOM.

const cache = new Map();

async function req(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export async function getOptions() {
  return req("/api/options");
}

export async function getShortlist(params = {}) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      sp.set(k, v);
    }
  }
  const qs = sp.toString();
  return req(`/api/shortlist${qs ? `?${qs}` : ""}`);
}

export async function getArtist(id) {
  const key = `artist:${id}`;
  if (cache.has(key)) return cache.get(key);
  const data = await req(`/api/artist/${id}`);
  cache.set(key, data);
  return data;
}

export async function getTrend(id) {
  const key = `trend:${id}`;
  if (cache.has(key)) return cache.get(key);
  const data = await req(`/api/artist/${id}/trend`);
  cache.set(key, data);
  return data;
}

export async function getFans(id, n = 10) {
  const key = `fans:${id}:${n}`;
  if (cache.has(key)) return cache.get(key);
  const data = await req(`/api/artist/${id}/fans?n=${n}`);
  cache.set(key, data);
  return data;
}

export async function getTracks(id, n = 5) {
  const key = `tracks:${id}:${n}`;
  if (cache.has(key)) return cache.get(key);
  const data = await req(`/api/artist/${id}/tracks?n=${n}`);
  cache.set(key, data);
  return data;
}
