// === DOM REFERENCES ===
const challengeSelect   = document.getElementById("challengeSelect");
const contentTypeSelect = document.getElementById("contentTypeSelect");
const domainSelect      = document.getElementById("domainSelect");
const difficultySelect  = document.getElementById("difficultySelect");
const deployBtn         = document.getElementById("deployBtn");
const resetBtn          = document.getElementById("resetBtn");
const refreshBtn        = document.getElementById("refreshBtn");
const userIdInput       = document.getElementById("userId");
const rawPayload        = document.getElementById("rawPayload");
const flashMessage      = document.getElementById("flashMessage");
const requestIdChip     = document.getElementById("requestIdChip");
const lastActionChip    = document.getElementById("lastActionChip");
const summaryChips      = document.getElementById("summaryChips");
const themeToggle       = document.getElementById("themeToggle");

const navDashboard = document.getElementById("navDashboard");
const navGuide     = document.getElementById("navGuide");
const navAbout     = document.getElementById("navAbout");
const dashboardView = document.getElementById("dashboardView");
const guideView     = document.getElementById("guideView");
const aboutView     = document.getElementById("aboutView");

const auditAction   = document.getElementById("auditAction");
const auditStatus   = document.getElementById("auditStatus");
const auditRequest  = document.getElementById("auditRequest");
const auditApplyBtn = document.getElementById("auditApplyBtn");
const auditClearBtn = document.getElementById("auditClearBtn");
const auditPrevBtn  = document.getElementById("auditPrevBtn");
const auditNextBtn  = document.getElementById("auditNextBtn");
const auditList     = document.getElementById("auditList");
const auditMeta     = document.getElementById("auditMeta");

const labIdEl       = document.getElementById("labId");
const labStateEl    = document.getElementById("labState");
const targetIpEl    = document.getElementById("targetIp");
const attackerIpEl  = document.getElementById("attackerIp");

// === STATE ===
let activeLabId   = null;
let lastRequestId = null;
let auditOffset   = 0;
const auditLimit  = 6;
let allContent    = [];
let pollingTimer  = null;

// === THEME ===
function applyTheme(mode) {
  document.documentElement.setAttribute("data-theme", mode);
  localStorage.setItem("cyberforge-theme", mode);
  themeToggle.checked = mode === "dark";
}

function initTheme() {
  const saved = localStorage.getItem("cyberforge-theme");
  if (saved === "dark" || saved === "light") { applyTheme(saved); return; }
  applyTheme(window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

themeToggle.addEventListener("change", () => applyTheme(themeToggle.checked ? "dark" : "light"));

// === REQUEST ID ===
function nextRequestId() {
  return window.crypto?.randomUUID?.() ?? `cf-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeHeaders(requestId) {
  const h = { "Content-Type": "application/json" };
  if (requestId) h["X-Request-ID"] = requestId;
  return h;
}

function getResponseRequestId(response) {
  return response.headers.get("X-Request-ID") || lastRequestId;
}

function updateRequestIdChip(requestId) {
  lastRequestId = requestId;
  requestIdChip.textContent = `Request: ${requestId ? requestId.slice(0, 8) + "…" : "-"}`;
}

// === FLASH + CHIP ===
const chipStateMap = {
  "idle":              "",
  "deploy":            "chip-warn",
  "deploy:success":    "chip-success",
  "deploy:failed":     "chip-danger",
  "reset":             "chip-warn",
  "reset:success":     "chip-success",
  "reset:failed":      "chip-danger",
  "refresh":           "chip-secondary",
  "filter":            "",
  "audit":             "",
  "boot:failed":       "chip-danger",
};

function setFlash(message, action = "idle") {
  flashMessage.textContent = message;
  lastActionChip.textContent = action.toUpperCase();
  // Remove previous state classes
  lastActionChip.className = "chip";
  const cls = chipStateMap[action];
  if (cls) lastActionChip.classList.add(cls);
}

// === FILTERS ===
function rebuildFilterOptions() {
  const currentDomain     = domainSelect.value || "all";
  const currentDifficulty = difficultySelect.value || "all";

  const domains      = [...new Set(allContent.map(i => i.domain || "uncategorized"))].sort();
  const difficulties = [...new Set(allContent.map(i => i.difficulty || "unknown"))].sort();

  domainSelect.innerHTML = '<option value="all">All Domains</option>';
  for (const d of domains) {
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    domainSelect.appendChild(o);
  }

  difficultySelect.innerHTML = '<option value="all">All Difficulties</option>';
  for (const d of difficulties) {
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    difficultySelect.appendChild(o);
  }

  domainSelect.value     = domains.includes(currentDomain) ? currentDomain : "all";
  difficultySelect.value = difficulties.includes(currentDifficulty) ? currentDifficulty : "all";
}

function applyContentFilters(content) {
  const type       = contentTypeSelect.value;
  const domain     = domainSelect.value;
  const difficulty = difficultySelect.value;
  return content.filter(item => {
    if (type !== "all" && (item.content_type || "independent") !== type) return false;
    if (domain !== "all" && (item.domain || "uncategorized") !== domain) return false;
    if (difficulty !== "all" && (item.difficulty || "unknown") !== difficulty) return false;
    return true;
  });
}

// === API: CHALLENGES ===
async function fetchChallenges() {
  const response = await fetch("/api/v1/challenges");
  if (!response.ok) throw new Error(`Failed to load challenges: ${response.status}`);
  allContent = await response.json();
  rebuildFilterOptions();
  renderChallengeOptions();
}

function renderChallengeOptions() {
  const filtered = applyContentFilters(allContent);
  challengeSelect.innerHTML = "";
  if (!filtered.length) {
    const o = document.createElement("option");
    o.value = ""; o.textContent = "No content for selected filters";
    challengeSelect.appendChild(o);
    return;
  }
  for (const c of filtered) {
    const o = document.createElement("option");
    o.value = c.id;
    const tag = c.content_type === "killchain" ? "KC" : "CH";
    const diff = c.difficulty ? ` · ${c.difficulty}` : "";
    o.textContent = `[${tag}] ${c.name}${diff}`;
    o.title = `${c.name} (${c.id})${c.description ? " — " + c.description : ""}`;
    challengeSelect.appendChild(o);
  }
}

// === API: CATALOG SUMMARY ===
async function fetchCatalogSummary() {
  const response = await fetch("/api/v1/catalog/summary");
  if (!response.ok) throw new Error(`Catalog summary failed: ${response.status}`);
  const summary = await response.json();
  const content = summary.content || {};

  summaryChips.innerHTML = "";
  const chips = [
    { label: `Independent: ${content.independent ?? 0}`, cls: "" },
    { label: `Killchains: ${content.killchain ?? 0}`, cls: "chip-secondary" },
    { label: `Total: ${content.total ?? 0}`, cls: "" },
  ];
  for (const { label, cls } of chips) {
    const chip = document.createElement("span");
    chip.className = cls ? `chip ${cls}` : "chip";
    chip.textContent = label;
    summaryChips.appendChild(chip);
  }

  // Also show domain breakdown if available
  const domains = summary.domains || {};
  for (const [domain, count] of Object.entries(domains)) {
    const chip = document.createElement("span");
    chip.className = "chip chip-ghost";
    chip.textContent = `${domain}: ${count}`;
    chip.title = `${count} challenges in domain: ${domain}`;
    summaryChips.appendChild(chip);
  }
}

// === API: AUDIT ===
async function fetchAuditEvents() {
  const params = new URLSearchParams({
    limit:  String(auditLimit),
    offset: String(auditOffset),
  });
  if (auditAction.value)        params.set("action",     auditAction.value);
  if (auditStatus.value)        params.set("status",     auditStatus.value);
  if (auditRequest.value.trim()) params.set("request_id", auditRequest.value.trim());

  const response = await fetch(`/api/v1/audit/events?${params}`);
  if (!response.ok) throw new Error(`Audit load failed: ${response.status}`);

  const payload = await response.json();
  renderAuditItems(payload.items || []);

  const total = payload.total || 0;
  const start = total ? payload.offset + 1 : 0;
  const end   = Math.min(total, payload.offset + (payload.items || []).length);
  auditMeta.textContent = total ? `Showing ${start}–${end} of ${total} events` : "No events yet.";

  auditPrevBtn.disabled = payload.offset <= 0;
  auditNextBtn.disabled = (payload.offset + auditLimit) >= total;
}

function renderAuditItems(items) {
  if (!items.length) {
    auditList.innerHTML = `<div class="audit-item"><span class="audit-meta">No audit events match these filters.</span></div>`;
    return;
  }
  auditList.innerHTML = items.map(item => {
    const requestId   = item.details?.request_id ? item.details.request_id.slice(0, 8) + "…" : "-";
    const challengeId = item.details?.challenge_id || "-";
    const error       = item.details?.error ? `<p class="audit-meta audit-error">⚠ ${item.details.error}</p>` : "";
    return `
      <article class="audit-item">
        <div class="audit-head">
          <span class="audit-title">${item.action}</span>
          <span class="audit-status ${item.status}">${item.status}</span>
        </div>
        <p class="audit-meta">User: <strong>${item.user_id || "-"}</strong> | Lab: <strong>${item.lab_id || "-"}</strong></p>
        <p class="audit-meta">Challenge: ${challengeId}</p>
        <p class="audit-meta">Req: ${requestId}</p>
        <p class="audit-meta">${new Date(item.created_at).toLocaleString()}</p>
        ${error}
      </article>`;
  }).join("");
}

// === SESSION STATE ===
const STATE_COLORS = {
  active:     "state-active",
  deploying:  "state-deploying",
  resetting:  "state-resetting",
  failed:     "state-failed",
  terminated: "state-terminated",
  idle:       "state-idle",
};

function setSessionState(session) {
  activeLabId = session?.id || null;
  const state = (session?.state || "").toLowerCase();

  // Only allow reset when lab is active
  resetBtn.disabled = state !== "active";

  labIdEl.textContent = session?.id || "-";

  // State pill gets a proper colour class
  labStateEl.textContent = state || "-";
  labStateEl.className = "state-pill " + (STATE_COLORS[state] || "");

  // Connection data from provisioner
  const conn = session?.connection || {};
  targetIpEl.textContent   = conn.target_ip   || conn.target_vm   || "-";
  attackerIpEl.textContent = conn.attacker_ip  || conn.attacker_vm || "-";

  rawPayload.textContent = session ? JSON.stringify(session, null, 2) : "No session yet.";

  // Surface error state to user
  if (state === "failed" && session?.last_error) {
    setFlash(`Lab failed: ${session.last_error}`, "deploy:failed");
  }

  // Start polling when lab is in a transient state
  if (["deploying", "resetting"].includes(state)) {
    startPolling(session.id);
  } else {
    stopPolling();
  }
}

// === POLLING for transient states ===
function startPolling(labId) {
  stopPolling();
  pollingTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/v1/labs/${labId}`);
      if (!res.ok) return;
      const session = await res.json();
      setSessionState(session);
      const s = (session?.state || "").toLowerCase();
      if (!["deploying", "resetting"].includes(s)) {
        stopPolling();
        await fetchAuditEvents();
      }
    } catch (_) {
      // ignore transient polling errors
    }
  }, 3000);
}

function stopPolling() {
  if (pollingTimer !== null) { clearInterval(pollingTimer); pollingTimer = null; }
}

// === DEPLOY ===
async function deployLab() {
  const userId = userIdInput.value.trim();
  if (!userId) { setFlash("Operator ID is required.", "idle"); userIdInput.focus(); return; }
  const challengeId = challengeSelect.value;
  if (!challengeId) { setFlash("Select a challenge first.", "idle"); return; }

  setLoading(deployBtn, true, "Deploying…");
  const requestId = nextRequestId();
  updateRequestIdChip(requestId);
  setFlash("Deploying lab…", "deploy");

  try {
    const response = await fetch("/api/v1/labs/deploy", {
      method: "POST",
      headers: makeHeaders(requestId),
      body: JSON.stringify({ user_id: userId, challenge_id: challengeId }),
    });

    // Parse the body regardless of status code — backend returns session even on failure
    let session;
    try { session = await response.json(); } catch { session = null; }

    if (!response.ok) {
      const detail = session?.detail || JSON.stringify(session) || response.statusText;
      throw new Error(detail);
    }

    updateRequestIdChip(getResponseRequestId(response));
    setSessionState(session);

    if (session?.state === "failed") {
      setFlash(`Deploy finished with errors: ${session.last_error || "unknown"}`, "deploy:failed");
    } else {
      setFlash("Lab deployed successfully.", "deploy:success");
    }
    await fetchAuditEvents();
  } catch (error) {
    rawPayload.textContent = `Deploy Error:\n${error.message}`;
    setFlash(`Deploy failed: ${error.message}`, "deploy:failed");
  } finally {
    setLoading(deployBtn, false, "Deploy Lab");
  }
}

// === RESET ===
async function resetLab() {
  if (!activeLabId) return;

  setLoading(resetBtn, true, "Resetting…");
  const requestId = nextRequestId();
  updateRequestIdChip(requestId);
  setFlash("Resetting lab…", "reset");

  try {
    const response = await fetch(`/api/v1/labs/${activeLabId}/reset`, {
      method: "POST",
      headers: makeHeaders(requestId),
    });

    let session;
    try { session = await response.json(); } catch { session = null; }

    if (!response.ok) {
      const detail = session?.detail || JSON.stringify(session) || response.statusText;
      throw new Error(detail);
    }

    updateRequestIdChip(getResponseRequestId(response));
    setSessionState(session);

    if (session?.state === "failed") {
      setFlash(`Reset finished with errors: ${session.last_error || "unknown"}`, "reset:failed");
    } else {
      setFlash("Lab reset completed.", "reset:success");
    }
    await fetchAuditEvents();
  } catch (error) {
    rawPayload.textContent = `Reset Error:\n${error.message}`;
    setFlash(`Reset failed: ${error.message}`, "reset:failed");
  } finally {
    setLoading(resetBtn, false, "Reset Lab");
  }
}

// === LOADING STATE HELPER ===
function setLoading(btn, loading, label) {
  btn.disabled = loading;
  btn.textContent = label;
  btn.setAttribute("aria-busy", loading ? "true" : "false");
}

// === EVENT LISTENERS ===
deployBtn.addEventListener("click", deployLab);
resetBtn.addEventListener("click", resetLab);

refreshBtn.addEventListener("click", async () => {
  setLoading(refreshBtn, true, "Refreshing…");
  try {
    await fetchChallenges();
    await fetchCatalogSummary();
    setFlash("Challenge catalog refreshed.", "refresh");
  } catch (error) {
    rawPayload.textContent = `Refresh Error:\n${error.message}`;
    setFlash("Could not refresh challenges.", "boot:failed");
  } finally {
    setLoading(refreshBtn, false, "Refresh Challenges");
  }
});

contentTypeSelect.addEventListener("change", () => {
  renderChallengeOptions();
  setFlash("Content type filter applied.", "filter");
});

domainSelect.addEventListener("change", () => {
  renderChallengeOptions();
  setFlash("Domain filter applied.", "filter");
});

difficultySelect.addEventListener("change", () => {
  renderChallengeOptions();
  setFlash("Difficulty filter applied.", "filter");
});

auditApplyBtn.addEventListener("click", async () => {
  auditOffset = 0;
  try {
    await fetchAuditEvents();
    setFlash("Audit filters applied.", "audit");
  } catch (error) {
    setFlash("Could not load audit events.", "boot:failed");
  }
});

auditClearBtn.addEventListener("click", async () => {
  auditAction.value = ""; auditStatus.value = ""; auditRequest.value = "";
  auditOffset = 0;
  try {
    await fetchAuditEvents();
    setFlash("Audit filters cleared.", "audit");
  } catch (error) {
    setFlash("Could not load audit events.", "boot:failed");
  }
});

auditPrevBtn.addEventListener("click", async () => {
  auditOffset = Math.max(0, auditOffset - auditLimit);
  try { await fetchAuditEvents(); } catch (_) {}
});

auditNextBtn.addEventListener("click", async () => {
  auditOffset += auditLimit;
  try { await fetchAuditEvents(); } catch (_) {}
});

function switchTab(activeBtn, showView) {
  // Update buttons
  [navDashboard, navGuide, navAbout].forEach(b => b.classList.remove("active"));
  activeBtn.classList.add("active");
  // Update views
  [dashboardView, guideView, aboutView].forEach(v => v.style.display = "none");
  showView.style.display = "block";
}

navDashboard.addEventListener("click", () => switchTab(navDashboard, dashboardView));
navGuide.addEventListener("click", () => switchTab(navGuide, guideView));
navAbout.addEventListener("click", () => switchTab(navAbout, aboutView));

// === BOOT SEQUENCE ===
(async () => {
  initTheme();
  setFlash("Booting…", "idle");

  try {
    await fetchChallenges();
  } catch (e) {
    rawPayload.textContent = `Boot Error:\n${e.message}`;
    setFlash("Could not load challenge catalog.", "boot:failed");
  }

  try {
    await fetchCatalogSummary();
  } catch (e) {
    // non-fatal, chips just won't populate
  }

  try {
    await fetchAuditEvents();
    setFlash("Ready.", "idle");
  } catch (e) {
    setFlash("Could not load audit events.", "boot:failed");
  }
})();
