"use strict";

// --- tiny fetch helper -------------------------------------------------
async function api(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// --- DOM shortcuts -----------------------------------------------------
const $ = (id) => document.getElementById(id);
const seasonSel = $("season");
const roundSel = $("round");
const tabsNav = $("tabs");
const panel = $("panel");

// --- app state ---------------------------------------------------------
let schedule = []; // rounds for the selected season
let current = null; // selected round object
let activeTab = "race";
let lapChart = null; // Chart.js instance, destroyed on tab switch

// Tabs available depending on whether the season has lap data (2018+).
const BASE_TABS = [
  { id: "race", label: "Race" },
  { id: "quali", label: "Qualifying" },
  { id: "sprint", label: "Sprint" },
  { id: "standings", label: "Standings" },
];
const LAP_TABS = [
  { id: "practice-laps", label: "Practice laps" },
  { id: "quali-laps", label: "Quali laps" },
  { id: "race-laps", label: "Race laps" },
];

// --- rendering helpers -------------------------------------------------
function table(rows, columns) {
  if (!rows || rows.length === 0) return null;
  const cols = columns || Object.keys(rows[0]);
  const t = document.createElement("table");
  t.innerHTML =
    "<thead><tr>" +
    cols.map((c) => `<th>${c}</th>`).join("") +
    "</tr></thead><tbody>" +
    rows
      .map(
        (r) =>
          "<tr>" +
          cols.map((c) => `<td>${r[c] ?? ""}</td>`).join("") +
          "</tr>"
      )
      .join("") +
    "</tbody>";
  return t;
}

function info(msg) {
  const p = document.createElement("p");
  p.className = "info";
  p.textContent = msg;
  return p;
}

function clearPanel() {
  if (lapChart) {
    lapChart.destroy();
    lapChart = null;
  }
  panel.innerHTML = "";
}

// --- panel renderers ---------------------------------------------------
async function renderResults() {
  const rows = await api(`/api/results/${seasonSel.value}/${current.round}`);
  clearPanel();
  panel.append(
    table(rows) || info("No race classification available for this round.")
  );
}

async function renderQuali() {
  const rows = await api(`/api/qualifying/${seasonSel.value}/${current.round}`);
  clearPanel();
  panel.append(
    table(rows) ||
      info(
        "No qualifying data available (Jolpica coverage thins out before ~2003)."
      )
  );
}

async function renderSprint() {
  const rows = await api(`/api/sprint/${seasonSel.value}/${current.round}`);
  clearPanel();
  panel.append(table(rows) || info("No sprint at this weekend."));
}

async function renderStandings() {
  const data = await api(`/api/standings/${seasonSel.value}/${current.round}`);
  clearPanel();
  const wrap = document.createElement("div");
  wrap.className = "two-col";

  const left = document.createElement("div");
  left.innerHTML = "<h3>Drivers after this round</h3>";
  left.append(
    table(data.drivers) || info("No driver standings available.")
  );

  const right = document.createElement("div");
  right.innerHTML = "<h3>Constructors after this round</h3>";
  right.append(
    table(data.constructors) ||
      info("No constructor standings (pre-1958 seasons have drivers only).")
  );

  wrap.append(left, right);
  panel.append(wrap);
}

// Distinct colors for chart lines, cycled per driver.
function colorFor(i) {
  const hue = (i * 47) % 360;
  return `hsl(${hue} 70% 55%)`;
}

async function renderLaps(group) {
  const data = await api(
    `/api/laps/${seasonSel.value}/${current.round}/${group}`
  );
  clearPanel();

  if (!data.available || data.available.length === 0) {
    panel.append(
      info(
        `No lap data ingested for this session yet. From the project root run: python src/ingest_laps.py ${seasonSel.value} ${current.round}`
      )
    );
    return;
  }

  // Session switcher if more than one code is present.
  if (data.available.length > 1) {
    const bar = document.createElement("div");
    bar.className = "session-switch";
    data.available.forEach((code) => {
      const b = document.createElement("button");
      b.textContent = code;
      b.className = code === data.code ? "active" : "";
      b.onclick = () => renderLapsCode(group, code);
      bar.append(b);
    });
    panel.append(bar);
  }

  renderLapData(data);
}

async function renderLapsCode(group, code) {
  const data = await api(
    `/api/laps/${seasonSel.value}/${current.round}/${group}?code=${code}`
  );
  clearPanel();
  if (data.available.length > 1) {
    const bar = document.createElement("div");
    bar.className = "session-switch";
    data.available.forEach((c) => {
      const b = document.createElement("button");
      b.textContent = c;
      b.className = c === data.code ? "active" : "";
      b.onclick = () => renderLapsCode(group, c);
      bar.append(b);
    });
    panel.append(bar);
  }
  renderLapData(data);
}

function renderLapData(data) {
  const h = document.createElement("h3");
  h.textContent = `${data.label || data.code} — lap times (seconds)`;
  panel.append(h);

  // Build a Chart.js line dataset per driver from the long-form series.
  if (data.series && data.series.length) {
    const byDriver = {};
    const lapSet = new Set();
    data.series.forEach((p) => {
      (byDriver[p.driver] ||= {})[p.lap] = p.seconds;
      lapSet.add(p.lap);
    });
    const laps = [...lapSet].sort((a, b) => a - b);
    const datasets = Object.keys(byDriver).map((driver, i) => ({
      label: driver,
      data: laps.map((l) => byDriver[driver][l] ?? null),
      borderColor: colorFor(i),
      borderWidth: 1.5,
      pointRadius: 0,
      spanGaps: true,
    }));

    const canvas = document.createElement("canvas");
    canvas.height = 120;
    panel.append(canvas);
    lapChart = new Chart(canvas, {
      type: "line",
      data: { labels: laps, datasets },
      options: {
        responsive: true,
        interaction: { mode: "nearest", intersect: false },
        scales: { x: { title: { display: true, text: "Lap" } } },
        plugins: { legend: { labels: { boxWidth: 12 } } },
      },
    });
  }

  if (data.fastest && data.fastest.length) {
    const h2 = document.createElement("h3");
    h2.textContent = "Fastest lap per driver";
    panel.append(h2, table(data.fastest));
  }
}

// --- tab wiring --------------------------------------------------------
const RENDERERS = {
  race: renderResults,
  quali: renderQuali,
  sprint: renderSprint,
  standings: renderStandings,
  "practice-laps": () => renderLaps("practice"),
  "quali-laps": () => renderLaps("quali"),
  "race-laps": () => renderLaps("race"),
};

function buildTabs() {
  const tabs = current.hasLaps ? [...BASE_TABS, ...LAP_TABS] : BASE_TABS;
  if (!tabs.find((t) => t.id === activeTab)) activeTab = "race";
  tabsNav.innerHTML = "";
  tabs.forEach((t) => {
    const b = document.createElement("button");
    b.textContent = t.label;
    b.className = t.id === activeTab ? "active" : "";
    b.onclick = () => {
      activeTab = t.id;
      buildTabs();
      showTab();
    };
    tabsNav.append(b);
  });
}

async function showTab() {
  if (current.isFuture) {
    clearPanel();
    panel.append(
      info(
        current.date
          ? `This race hasn't happened yet — scheduled for ${current.date}.`
          : "This race hasn't happened yet."
      )
    );
    return;
  }
  clearPanel();
  panel.append(info("Loading…"));
  try {
    await RENDERERS[activeTab]();
  } catch (e) {
    clearPanel();
    panel.append(info(`Error loading data: ${e.message}`));
  }
}

// --- selection wiring --------------------------------------------------
function selectRound() {
  current = schedule[roundSel.value];
  $("race-title").textContent = `${seasonSel.value} ${current.raceName} — Round ${current.round}`;
  $("race-meta").textContent =
    `${current.circuitName} — ${current.locality}, ${current.country} · ${current.date}`;
  buildTabs();
  showTab();
}

async function loadSeason(year) {
  schedule = await api(`/api/schedule/${year}`);
  roundSel.innerHTML = "";
  if (schedule.length === 0) {
    $("race-title").textContent = `No rounds found for ${year}.`;
    panel.innerHTML = "";
    return;
  }
  schedule.forEach((r, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = `R${r.round} — ${r.raceName} (${r.date})`;
    roundSel.append(opt);
  });
  roundSel.value = 0;
  selectRound();
}

// --- boot --------------------------------------------------------------
async function boot() {
  try {
    await api("/api/health");
    $("api-status").textContent = `Connected to API: ${API_BASE}`;
  } catch (e) {
    $("api-status").textContent = `⚠ Cannot reach API at ${API_BASE} (${e.message})`;
  }

  try {
    const years = await api("/api/seasons");
    years.forEach((y) => {
      const opt = document.createElement("option");
      opt.value = y;
      opt.textContent = y;
      seasonSel.append(opt);
    });
    seasonSel.value = years[0];
    await loadSeason(years[0]);
  } catch (e) {
    $("race-title").textContent = `Failed to load seasons: ${e.message}`;
  }
}

seasonSel.addEventListener("change", () => loadSeason(seasonSel.value));
roundSel.addEventListener("change", selectRound);
boot();
