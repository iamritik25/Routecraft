// ============================================================
// RouteCraft v2 — frontend  (surge · ETA confidence · ML badge)
// ============================================================

const MODE_COLORS = { walk:"#5f6368", auto:"#0b8043", cab:"#1a73e8", bus:"#e37400", metro:"#9334e6" };
const MODE_LABELS = { walk:"Walk", auto:"Auto", cab:"Cab", bus:"Bus", metro:"Metro" };

const ICON = {
    walk:  `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13" cy="4" r="2"/><path d="M10 22l2-8 3 2 1 6"/><path d="M7 14l3-5 3 2"/><path d="M9 19l-2 3"/></svg>`,
    auto:  `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="10" width="18" height="7" rx="2"/><path d="M6 10V6h9l3 4"/><circle cx="7" cy="19" r="1.5"/><circle cx="17" cy="19" r="1.5"/></svg>`,
    cab:   `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l2-5h10l2 5"/><rect x="3" y="13" width="18" height="6" rx="2"/><circle cx="7" cy="20" r="1.5"/><circle cx="17" cy="20" r="1.5"/></svg>`,
    bus:   `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="13" rx="2"/><path d="M4 9h16"/><circle cx="8" cy="20" r="1.5"/><circle cx="16" cy="20" r="1.5"/><path d="M8 17v2"/><path d="M16 17v2"/></svg>`,
    metro: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="15" rx="4"/><path d="M9 21l3-3 3 3"/><circle cx="9" cy="11" r="1"/><circle cx="15" cy="11" r="1"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
    rupee: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h12M6 8h12M6 8c4 0 7 1 7 4s-3 4-7 4h-1l7 8"/></svg>`,
    route: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M6 8.5v3A4.5 4.5 0 0 0 10.5 16h3A4.5 4.5 0 0 1 18 20.5"/></svg>`,
    brain: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5 3 3 0 0 0 2 5v1a3 3 0 0 0 6 0V4"/><path d="M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 2 5 3 3 0 0 1-2 5v1a3 3 0 0 1-6 0"/></svg>`,
    warn:  `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.7a2 2 0 0 1 3.4 0l8 14a2 2 0 0 1-1.7 3H4a2 2 0 0 1-1.7-3z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
    surge: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`,
    eta:   `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18M3 6l9-3 9 3M3 18l9 3 9-3"/></svg>`,
};

// ============================================================
// Search
// ============================================================

async function findRoute() {
    const source      = (document.getElementById("source").value || "").trim();
    const destination = (document.getElementById("destination").value || "").trim();
    const preference  = document.getElementById("preference").value;
    const weather     = document.getElementById("weather").value;
    const hour        = parseInt(document.getElementById("hour").value || "9", 10);
    const statusEl    = document.getElementById("status");

    if (!source || !destination) { statusEl.textContent = "Please enter both source and destination."; return; }
    if (source === destination)   { statusEl.textContent = "Source and destination should be different."; return; }

    statusEl.innerHTML = `<span class="spinner"></span> Computing optimal routes…`;
    const btn = document.getElementById("findRouteBtn");
    btn.disabled = true;

    try {
        const resp = await fetch("/v1/route", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source, destination, preference, weather, hour }),
        });
        const data = await resp.json();
        if (!resp.ok) { statusEl.textContent = (data && data.error) || `Request failed (${resp.status})`; return; }
        statusEl.textContent = "";
        renderAll(data, { hour, source, destination });
    } catch (err) {
        console.error(err);
        statusEl.textContent = "Failed to compute routes. Check console for details.";
    } finally {
        btn.disabled = false;
    }
}

// ============================================================
// Render orchestration
// ============================================================

let _lastData = null;
let _activeRouteKey = null;
let _requestHour = 9;

function renderAll(data, meta) {
    _lastData = data;
    _requestHour = (meta && meta.hour != null) ? meta.hour : 9;
    renderSurge(data.surge);
    renderMlStatus(data.ml, data.ab_backend);
    renderResultsPanel(data);
    renderMap(data);
}

// ---- Surge pricing banner ----
function renderSurge(surge) {
    const el = document.getElementById("surgePanel");
    if (!el || !surge) { if (el) el.hidden = true; return; }

    const mult = surge.multiplier || 1.0;
    const label = surge.label || "";
    // colour classes driven by multiplier
    let cls = "surge-normal";
    if (mult >= 2.5) cls = "surge-critical";
    else if (mult >= 1.8) cls = "surge-high";
    else if (mult >= 1.3) cls = "surge-moderate";

    el.hidden = false;
    el.className = `panel panel-surge ${cls}`;
    el.innerHTML = `
        <div class="surge-icon">${ICON.surge}</div>
        <div class="surge-body">
            <div class="surge-label">${label}</div>
            <div class="surge-mult">${mult.toFixed(1)}× surge · fares adjusted</div>
        </div>`;
}

// ---- ML status card ----
function renderMlStatus(ml, abBackend) {
    const el = document.getElementById("mlStatus");
    if (!el) return;
    if (!ml) { el.hidden = true; return; }

    if (ml.used) {
        let backendLabel = "scikit-learn GBM";
        if (ml.backend === "pytorch-mps")  backendLabel = "PyTorch MLP · GPU";
        else if (ml.backend === "lightgbm") backendLabel = "LightGBM · CPU";
        else if (ml.backend === "sklearn-gbm") backendLabel = "scikit-learn GBM";

        const areas = (ml.areas || []).slice(0, 4).join(", ") + ((ml.areas || []).length > 4 ? ", …" : "");
        const abTag = abBackend ? `<span class="ab-tag">A/B: ${abBackend}</span>` : "";
        el.hidden = false;
        el.className = "panel panel-ml";
        el.innerHTML = `
            <div class="ml-icon">${ICON.brain}</div>
            <div>
                <div class="ml-title">ML traffic model active ${abTag}</div>
                <div class="ml-sub">${backendLabel} · ${ml.hits} segments enriched · ${areas}</div>
            </div>`;
    } else {
        el.hidden = false;
        el.className = "panel panel-ml heuristic";
        el.innerHTML = `
            <div class="ml-icon">${ICON.warn}</div>
            <div>
                <div class="ml-title">Heuristic model</div>
                <div class="ml-sub">No trained area matched this trip — using time-of-day rules.</div>
            </div>`;
    }
}

// ---- Results panel ----
const ROUTE_OPTIONS = [
    { k: "balanced",       label: "Balanced" },
    { k: "fastest",        label: "Fastest" },
    { k: "cheapest",       label: "Cheapest" },
    { k: "cab_only",       label: "Cab" },
    { k: "metro_only",     label: "Metro" },
    { k: "metro_plus_cab", label: "Metro+Cab" },
    { k: "bus_only",       label: "Bus" },
];

function availableRoutes(data) {
    return ROUTE_OPTIONS.filter((o) => {
        const r = data[o.k];
        return r && (r.condensed_path || []).length >= 2 && r.total_time != null;
    });
}

function renderResultsPanel(data) {
    const panel = document.getElementById("resultsPanel");
    const empty = document.getElementById("emptyState");
    const tabs  = document.getElementById("routeTabs");
    const active = document.getElementById("activeRoute");

    const avail = availableRoutes(data);
    if (avail.length === 0) { panel.hidden = true; empty.hidden = false; return; }
    panel.hidden = false;
    empty.hidden = true;

    const preferKey = data.preferred || "balanced";
    const activeKey = avail.find((o) => o.k === preferKey)?.k || avail[0].k;
    _activeRouteKey = activeKey;

    tabs.innerHTML = avail.map((o) => {
        const r = data[o.k];
        return `<button class="tab${o.k === activeKey ? " active" : ""}" data-key="${o.k}">
            <span class="tab-label">${o.label}</span>
            <span class="tab-meta">${Math.round(r.total_time)} min · ₹${Math.round(r.total_cost)}</span>
        </button>`;
    }).join("");
    tabs.querySelectorAll(".tab").forEach((btn) => {
        btn.addEventListener("click", () => selectRoute(btn.getAttribute("data-key")));
    });

    active.innerHTML = renderActiveRoute(data[activeKey]);
}

function selectRoute(key) {
    if (!_lastData || !_lastData[key]) return;
    _activeRouteKey = key;
    document.querySelectorAll("#routeTabs .tab").forEach((b) => {
        b.classList.toggle("active", b.getAttribute("data-key") === key);
    });
    document.getElementById("activeRoute").innerHTML = renderActiveRoute(_lastData[key]);
    renderRouteOnMap(_lastData, key);
}

// ---- Active route card ----
function renderActiveRoute(route) {
    if (!route) return "";
    const minutes = Math.round(route.total_time);
    const cost    = Math.round(route.total_cost);
    const stops   = (route.condensed_path || []).length;
    const eta     = etaString(_requestHour, route.total_time);
    const modes   = uniqueModes(route);

    const modePills = modes.map((m) => `
        <span class="mode-pill" style="color:${MODE_COLORS[m]}">
            ${ICON[m] || ""} ${MODE_LABELS[m] || m}
        </span>`).join("");

    const etaBand  = renderETABand(route);
    const steps    = (route.edges || []).map((e) => renderStep(e)).join("");

    return `
        <div class="route-header">
            <div>
                <span class="route-time">${minutes}</span><span class="route-time-unit">min</span>
            </div>
            <div class="route-eta">Arrives <strong>${eta}</strong></div>
        </div>
        <div class="route-meta-row">
            <span class="meta-item">${ICON.rupee} ₹${cost}</span>
            <span class="meta-item">${ICON.route} ${stops} stops</span>
        </div>
        <div class="mode-pills">${modePills}</div>
        ${etaBand}
        <div class="steps">${steps}</div>
    `;
}

// ---- ETA Confidence Band (P10/P50/P90) ----
function renderETABand(route) {
    if (route.eta_p10 == null || route.eta_p90 == null) return "";

    const p10 = Math.round(route.eta_p10);
    const p50 = Math.round(route.eta_p50 || route.total_time);
    const p90 = Math.round(route.eta_p90);
    const conf = route.eta_confidence || "medium";

    const confColor = { high: "#34a853", medium: "#f9ab00", low: "#ea4335" }[conf] || "#9aa0a6";
    const confLabel = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" }[conf] || conf;

    // Visual bar: p10 to p90 as a percentage band within [0, p90*1.1]
    const max = p90 * 1.15;
    const left  = ((p10 / max) * 100).toFixed(1);
    const width = (((p90 - p10) / max) * 100).toFixed(1);
    const mid   = ((p50 / max) * 100).toFixed(1);

    return `
        <div class="eta-band">
            <div class="eta-band-header">
                ${ICON.eta}
                <span class="eta-band-title">ETA window</span>
                <span class="eta-band-conf" style="color:${confColor}">● ${confLabel}</span>
            </div>
            <div class="eta-band-track">
                <div class="eta-band-fill" style="left:${left}%;width:${width}%"></div>
                <div class="eta-band-marker" style="left:${mid}%" title="P50 (median)"></div>
            </div>
            <div class="eta-band-labels">
                <span>${ICON.clock} ${p10}m <span class="eta-label-sub">best</span></span>
                <span class="eta-p50-label">${p50}m <span class="eta-label-sub">median</span></span>
                <span>${p90}m <span class="eta-label-sub">worst</span></span>
            </div>
        </div>`;
}

function renderStep(edge) {
    const mode = inferModeFromDescription(edge.description);
    const fromClean = stripModeSuffix(edge.from);
    const toClean   = stripModeSuffix(edge.to);
    const mins = Math.round(edge.time_min);
    const cost = Math.round(edge.cost);
    const color = MODE_COLORS[mode] || "#5f6368";

    return `
        <div class="step">
            <div class="step-icon" style="background:${color}">${ICON[mode] || ICON.cab}</div>
            <div class="step-body">
                <div class="step-title">${capitalize(MODE_LABELS[mode] || mode)} · ${escapeHtml(fromClean)} → ${escapeHtml(toClean)}</div>
                <div class="step-sub">
                    <span>${mins} min</span>
                    <span class="dot">·</span>
                    <span>₹${cost}</span>
                </div>
            </div>
        </div>`;
}

function uniqueModes(route) {
    const seen = new Set(), out = [];
    (route.edges || []).forEach((e) => {
        const m = inferModeFromDescription(e.description);
        if (!seen.has(m)) { seen.add(m); out.push(m); }
    });
    return out;
}

function etaString(startHour, totalMin) {
    const total = startHour * 60 + Math.round(totalMin || 0);
    const h = Math.floor(total / 60) % 24;
    const m = total % 60;
    const d = new Date();
    d.setHours(h, m, 0, 0);
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function capitalize(s) { return (s || "").charAt(0).toUpperCase() + (s || "").slice(1); }
function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// ============================================================
// Map
// ============================================================

let _map = null;
let _layerGroup = null;

function ensureMap() {
    if (_map) return _map;
    _map = L.map("map", { scrollWheelZoom: true, zoomControl: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap contributors",
    }).addTo(_map);
    _map.setView([12.9716, 77.5946], 11);
    _layerGroup = L.layerGroup().addTo(_map);
    return _map;
}

function inferModeFromDescription(desc) {
    if (!desc) return "cab";
    const d = desc.toLowerCase();
    if (d.startsWith("walk"))  return "walk";
    if (d.startsWith("auto"))  return "auto";
    if (d.startsWith("bus"))   return "bus";
    if (d.startsWith("metro")) return "metro";
    return "cab";
}

function stripModeSuffix(loc) {
    if (!loc) return loc;
    return loc.replace(/\s*\([a-z_]+\)\s*$/i, "").trim();
}

function coordFor(name) {
    const coords = window.LOCATION_COORDS || {};
    if (!name) return null;
    if (coords[name]) return coords[name];
    const clean = stripModeSuffix(name);
    if (coords[clean]) return coords[clean];
    return null;
}

function makeEndpointMarker(letter) {
    const cls = letter === "A" ? "start" : "end";
    const icon = L.divIcon({
        className: "endpoint-marker",
        html: `<div class="endpoint-pin ${cls}"><span>${letter}</span></div>`,
        iconSize: [30, 38], iconAnchor: [15, 36], popupAnchor: [0, -34],
    });
    return L.marker([0, 0], { icon });
}

function renderMap(data) {
    const floating = document.getElementById("mapFloating");
    const avail = availableRoutes(data);
    if (avail.length === 0) { floating.hidden = true; return; }
    floating.hidden = false;
    buildRouteSwitcher(data);
    renderRouteOnMap(data, _activeRouteKey || avail[0].k);
}

function renderRouteOnMap(data, routeKey) {
    const route = data[routeKey];
    if (!route) return;

    const map = ensureMap();
    _layerGroup.clearLayers();

    const pathLocs  = route.condensed_path || [];
    const allLatLngs = [];

    if (pathLocs.length >= 2) {
        const startLL = coordFor(pathLocs[0]);
        const endLL   = coordFor(pathLocs[pathLocs.length - 1]);
        if (startLL) {
            makeEndpointMarker("A").setLatLng(startLL)
                .bindPopup(`<b>Start</b><br>${escapeHtml(pathLocs[0])}`).addTo(_layerGroup);
            allLatLngs.push(startLL);
        }
        if (endLL) {
            makeEndpointMarker("B").setLatLng(endLL)
                .bindPopup(`<b>End</b><br>${escapeHtml(pathLocs[pathLocs.length - 1])}`).addTo(_layerGroup);
            allLatLngs.push(endLL);
        }
        for (let i = 1; i < pathLocs.length - 1; i++) {
            const ll = coordFor(pathLocs[i]);
            if (ll) {
                L.circleMarker(ll, { radius: 5, color: "#fff", fillColor: "#1a73e8", fillOpacity: 1, weight: 2 })
                    .addTo(_layerGroup).bindTooltip(pathLocs[i]);
                allLatLngs.push(ll);
            }
        }

        // Draw coloured polyline segments by mode
        const edges = route.edges || [];
        let prevLL = startLL;
        edges.forEach((e) => {
            const mode  = inferModeFromDescription(e.description);
            const color = MODE_COLORS[mode] || "#1a73e8";
            const toLoc = stripModeSuffix(e.to);
            const toLL  = coordFor(toLoc);
            if (prevLL && toLL) {
                L.polyline([prevLL, toLL], { color, weight: 4, opacity: 0.85, dashArray: mode === "walk" ? "6 6" : null })
                    .addTo(_layerGroup)
                    .bindTooltip(`${MODE_LABELS[mode] || mode} · ${Math.round(e.time_min)} min · ₹${Math.round(e.cost)}`);
                prevLL = toLL;
            }
        });
    }

    if (allLatLngs.length >= 2) {
        setTimeout(() => { map.invalidateSize(); map.fitBounds(L.latLngBounds(allLatLngs), { padding: [60, 60] }); }, 40);
    } else if (allLatLngs.length === 1) {
        setTimeout(() => { map.invalidateSize(); map.setView(allLatLngs[0], 13); }, 40);
    }

    renderRouteStats(route);
    highlightActiveSwitcher(routeKey);
}

function renderRouteStats(route) {
    const el = document.getElementById("routeStats");
    if (!el) return;
    const cost  = route.total_cost != null ? `₹${Math.round(route.total_cost)}` : "—";
    const time  = route.total_time != null ? `${Math.round(route.total_time)}m` : "—";
    const stops = (route.condensed_path || []).length;
    const p90   = route.eta_p90 != null ? `${Math.round(route.eta_p90)}m` : "—";
    el.innerHTML = `
        <span class="stat"><span class="stat-k">P50</span><span class="stat-v">${time}</span></span>
        <span class="stat"><span class="stat-k">P90</span><span class="stat-v">${p90}</span></span>
        <span class="stat"><span class="stat-k">Cost</span><span class="stat-v">${cost}</span></span>
        <span class="stat"><span class="stat-k">Stops</span><span class="stat-v">${stops}</span></span>
    `;
}

function buildRouteSwitcher(data) {
    const el = document.getElementById("routeSwitcher");
    if (!el) return;
    const avail = availableRoutes(data);
    el.innerHTML = avail.map((o) => {
        const r = data[o.k];
        return `<button type="button" class="rs-pill" data-key="${o.k}">
            <span class="rs-label">${o.label}</span>
            <span class="rs-meta">${Math.round(r.total_time)}m · ₹${Math.round(r.total_cost)}</span>
        </button>`;
    }).join("");
    el.querySelectorAll(".rs-pill").forEach((btn) => {
        btn.addEventListener("click", () => selectRoute(btn.getAttribute("data-key")));
    });
    highlightActiveSwitcher(_activeRouteKey);
}

function highlightActiveSwitcher(key) {
    document.querySelectorAll("#routeSwitcher .rs-pill").forEach((btn) => {
        btn.classList.toggle("active", btn.getAttribute("data-key") === key);
    });
}

// ============================================================
// Bootstrap
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    ensureMap();
    document.getElementById("findRouteBtn").addEventListener("click", () => void findRoute());
    ["source", "destination"].forEach((id) => {
        document.getElementById(id).addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); findRoute(); }
        });
    });

    const getSourceDest = () => ({
        source:      (document.getElementById("source").value || "").trim(),
        destination: (document.getElementById("destination").value || "").trim(),
    });
    const openBooking = (path) => {
        const { source, destination } = getSourceDest();
        if (!source || !destination) return;
        window.open(`${path}?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`, "_blank");
    };
    document.getElementById("bookUberBtn").addEventListener("click",  () => openBooking("/book/uber"));
    document.getElementById("bookBmtcBtn").addEventListener("click",  () => openBooking("/book/bmtc"));
    document.getElementById("bookMetroBtn").addEventListener("click", () => openBooking("/book/metro"));
});
