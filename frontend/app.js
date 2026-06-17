"use strict";

// Chart.js theme so axes/legend are legible on the dark cards.
if (window.Chart) {
  Chart.defaults.color = "#6b7280";
  Chart.defaults.borderColor = "rgba(20,22,26,0.08)";
  Chart.defaults.font.family = "'Titillium Web', sans-serif";
}

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
  { id: "race", label: "Race", icon: "🏆" },
  { id: "quali", label: "Qualifying", icon: "⏱" },
  { id: "sprint", label: "Sprint", icon: "🏃" },
  { id: "standings", label: "Standings", icon: "📊" },
];
const LAP_TABS = [
  { id: "practice-laps", label: "Practice laps", icon: "🛞" },
  { id: "quali-laps", label: "Quali laps", icon: "⏱" },
  { id: "race-laps", label: "Race laps", icon: "🏁" },
];

// --- rendering helpers -------------------------------------------------

// Team accent colors keyed by constructor name (substring match, so
// "Red Bull Racing" and "Red Bull" both resolve). Fallback is grey.
const TEAM_COLORS = [
  [/red bull|^rb |racing bulls|alphatauri|toro rosso/i, "#3671c6"],
  [/ferrari/i, "#e8002d"],
  [/mercedes/i, "#27f4d2"],
  [/mclaren/i, "#ff8000"],
  [/aston/i, "#229971"],
  [/alpine/i, "#0093cc"],
  [/williams/i, "#64c4ff"],
  [/haas/i, "#b6babd"],
  [/sauber|kick|alfa romeo/i, "#52e252"],
  [/renault/i, "#fff500"],
  [/force india|racing point/i, "#f596c8"],
  [/lotus/i, "#ffb800"],
];
function teamColor(name) {
  const hit = TEAM_COLORS.find(([re]) => re.test(name || ""));
  return hit ? hit[1] : "#8a929e";
}

function esc(v) {
  return String(v ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// Position chip — podium gets a filled colored badge.
function posCell(v) {
  const r = String(v ?? "").trim();
  const podium = ["1", "2", "3"].includes(r) ? ` pos-badge-${r}` : "";
  return `<span class="pos-badge${podium}">${esc(r)}</span>`;
}

// Team name with a color dot.
function teamCell(v) {
  return (
    `<span class="team"><span class="team-dot" style="background:${teamColor(v)}"></span>` +
    `${esc(v)}</span>`
  );
}

// Status pill — "Finished" is solid red, anything else (lapped, DNF,
// accident…) is an outline pill.
function statusCell(v) {
  const s = String(v ?? "").trim();
  if (!s) return "";
  const finished = /^finished/i.test(s);
  const label = /\+\d+\s*lap/i.test(s) ? "Lapped" : s;
  return `<span class="pill ${finished ? "pill-done" : "pill-out"}">${esc(label)}</span>`;
}

// Per-column cell formatters (return HTML). Columns not listed are
// plain escaped text. Harmless for tables lacking these columns.
const CELL_FORMATTERS = {
  Pos: posCell,
  Constructor: teamCell,
  Team: teamCell,
  Status: statusCell,
};

function table(rows, columns) {
  if (!rows || rows.length === 0) return null;
  const cols = columns || Object.keys(rows[0]);
  const rankCol = cols[0] === "Pos" ? "Pos" : null;
  const t = document.createElement("table");
  t.innerHTML =
    "<thead><tr>" +
    cols.map((c) => `<th>${esc(c)}</th>`).join("") +
    "</tr></thead><tbody>" +
    rows
      .map((r) => {
        const rank = rankCol ? String(r[rankCol]).trim() : "";
        const cls = ["1", "2", "3"].includes(rank) ? ` class="pos-${rank}"` : "";
        const cells = cols
          .map((c) => {
            const fmt = CELL_FORMATTERS[c];
            const html = fmt ? fmt(r[c]) : esc(r[c]);
            return `<td class="col-${c.replace(/[^a-z]/gi, "")}">${html}</td>`;
          })
          .join("");
        return `<tr${cls}>${cells}</tr>`;
      })
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

    const chartBox = document.createElement("div");
    chartBox.className = "chart-box";
    const canvas = document.createElement("canvas");
    chartBox.append(canvas);
    panel.append(chartBox);
    lapChart = new Chart(canvas, {
      type: "line",
      data: { labels: laps, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
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
    b.innerHTML = `<span class="tab-icon">${t.icon || ""}</span>${t.label}`;
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
  $("hero-kicker").textContent =
    `${seasonSel.value} season · Round ${current.round}${current.country ? " · " + current.country : ""}`;
  $("race-title").textContent = current.raceName;
  $("race-meta").innerHTML =
    `<span class="meta-row"><span class="meta-ico">📍</span>${esc(current.circuitName)} — ${esc(current.locality)}, ${esc(current.country)}</span>` +
    `<span class="meta-row"><span class="meta-ico">📅</span>${esc(current.date)}</span>`;
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

// --- News page ---------------------------------------------------------
let newsLoaded = false;

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

async function loadNews(force = false) {
  if (newsLoaded && !force) return;
  const list = $("news-list");
  list.innerHTML = "";
  list.append(info("Loading latest F1 news…"));
  try {
    const data = await api("/api/news");
    list.innerHTML = "";
    if (!data.items || data.items.length === 0) {
      list.append(info("No news available right now."));
    } else {
      data.items.forEach((it) => list.append(newsCard(it)));
    }
    $("news-updated").textContent = data.fetchedAt
      ? `Updated ${timeAgo(data.fetchedAt)} · refreshes through the morning`
      : "";
    newsLoaded = true;
  } catch (e) {
    list.innerHTML = "";
    list.append(info(`Couldn't load news: ${e.message}`));
  }
}

function newsCard(it) {
  const a = document.createElement("a");
  a.className = "news-card";
  a.href = it.link;
  a.target = "_blank";
  a.rel = "noopener noreferrer";

  const meta = document.createElement("div");
  meta.className = "news-meta";
  meta.innerHTML =
    `<span class="news-source">${it.source}</span>` +
    (it.published ? `<span class="news-time">${timeAgo(it.published)}</span>` : "");

  const h = document.createElement("h3");
  h.className = "news-title";
  h.textContent = it.title;

  a.append(meta, h);
  if (it.summary) {
    const p = document.createElement("p");
    p.className = "news-summary";
    p.textContent = it.summary;
    a.append(p);
  }
  return a;
}

// --- Chat page ---------------------------------------------------------
const chatHistory = []; // [{role, content}] text turns sent to the API
let chatBusy = false;

function chatBubble(role, text) {
  const el = document.createElement("div");
  el.className = `chat-msg chat-${role}`;
  el.textContent = text;
  $("chat-log").append(el);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return el;
}

async function sendChat(text) {
  if (chatBusy || !text.trim()) return;
  chatBusy = true;
  $("chat-send").disabled = true;
  chatBubble("user", text);
  chatHistory.push({ role: "user", content: text });

  const pending = chatBubble("assistant", "…");
  pending.classList.add("chat-pending");
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = await res.json();
    pending.classList.remove("chat-pending");
    pending.textContent = data.reply;
    chatHistory.push({ role: "assistant", content: data.reply });
  } catch (e) {
    pending.classList.remove("chat-pending");
    pending.classList.add("chat-error");
    pending.textContent = `Couldn't get an answer: ${e.message}`;
  } finally {
    chatBusy = false;
    $("chat-send").disabled = false;
    $("chat-text").focus();
  }
}

let chatGreeted = false;
function initChat() {
  if (chatGreeted) return;
  chatGreeted = true;
  chatBubble(
    "assistant",
    "Hi! Ask me anything about F1 — race results, qualifying, championship standings, lap times, or the latest news."
  );
}

// --- top-level page switching -----------------------------------------
function showPage(page) {
  $("page-results").hidden = page !== "results";
  $("page-news").hidden = page !== "news";
  $("page-chat").hidden = page !== "chat";
  // Season/round controls only make sense on the results page.
  $("results-controls").style.display = page === "results" ? "" : "none";
  document
    .querySelectorAll("#pagenav button")
    .forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  if (page === "news") loadNews();
  if (page === "chat") initChat();
}

document.querySelectorAll("#pagenav button").forEach((b) => {
  b.addEventListener("click", () => showPage(b.dataset.page));
});

$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("chat-text").value;
  $("chat-text").value = "";
  sendChat(text);
});

seasonSel.addEventListener("change", () => loadSeason(seasonSel.value));
roundSel.addEventListener("change", selectRound);
boot();
