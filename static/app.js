const challengeSelect = document.getElementById("challengeSelect");
const contentTypeSelect = document.getElementById("contentTypeSelect");
const domainSelect = document.getElementById("domainSelect");
const difficultySelect = document.getElementById("difficultySelect");
const deployBtn = document.getElementById("deployBtn");
const resetBtn = document.getElementById("resetBtn");
const refreshBtn = document.getElementById("refreshBtn");
const userIdInput = document.getElementById("userId");
const rawPayload = document.getElementById("rawPayload");
const flashMessage = document.getElementById("flashMessage");
const requestIdChip = document.getElementById("requestIdChip");
const lastActionChip = document.getElementById("lastActionChip");
const summaryChips = document.getElementById("summaryChips");
const themeToggle = document.getElementById("themeToggle");

const auditAction = document.getElementById("auditAction");
const auditStatus = document.getElementById("auditStatus");
const auditRequest = document.getElementById("auditRequest");
const auditApplyBtn = document.getElementById("auditApplyBtn");
const auditClearBtn = document.getElementById("auditClearBtn");
const auditPrevBtn = document.getElementById("auditPrevBtn");
const auditNextBtn = document.getElementById("auditNextBtn");
const auditList = document.getElementById("auditList");
const auditMeta = document.getElementById("auditMeta");

const labIdEl = document.getElementById("labId");
const labStateEl = document.getElementById("labState");
const targetIpEl = document.getElementById("targetIp");
const attackerIpEl = document.getElementById("attackerIp");

let activeLabId = null;
let lastRequestId = null;
let auditOffset = 0;
const auditLimit = 6;
let allContent = [];

function rebuildFilterOptions() {
  const currentDomain = domainSelect.value || "all";
  const currentDifficulty = difficultySelect.value || "all";

  const domains = [...new Set(allContent.map((item) => item.domain || "uncategorized"))].sort();
  const difficulties = [...new Set(allContent.map((item) => item.difficulty || "unknown"))].sort();

  domainSelect.innerHTML = '<option value="all">All Domains</option>';
  for (const domain of domains) {
    const option = document.createElement("option");
    option.value = domain;
    option.textContent = domain;
    domainSelect.appendChild(option);
  }

  difficultySelect.innerHTML = '<option value="all">All Difficulties</option>';
  for (const difficulty of difficulties) {
    const option = document.createElement("option");
    option.value = difficulty;
    option.textContent = difficulty;
    difficultySelect.appendChild(option);
  }

  domainSelect.value = domains.includes(currentDomain) ? currentDomain : "all";
  difficultySelect.value = difficulties.includes(currentDifficulty) ? currentDifficulty : "all";
}

function applyContentFilters(content) {
  const selectedType = contentTypeSelect.value;
  const selectedDomain = domainSelect.value;
  const selectedDifficulty = difficultySelect.value;

  return content.filter((item) => {
    const type = item.content_type || "independent";
    const domain = item.domain || "uncategorized";
    const difficulty = item.difficulty || "unknown";

    if (selectedType !== "all" && type !== selectedType) {
      return false;
    }
    if (selectedDomain !== "all" && domain !== selectedDomain) {
      return false;
    }
    if (selectedDifficulty !== "all" && difficulty !== selectedDifficulty) {
      return false;
    }
    return true;
  });
}

function applyTheme(mode) {
  const root = document.documentElement;
  root.setAttribute("data-theme", mode);
  localStorage.setItem("cyberforge-theme", mode);
  themeToggle.checked = mode === "dark";
}

function initTheme() {
  const saved = localStorage.getItem("cyberforge-theme");
  if (saved === "dark" || saved === "light") {
    applyTheme(saved);
    return;
  }
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(prefersDark ? "dark" : "light");
}

function nextRequestId() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `cf-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setFlash(message, action = "idle") {
  flashMessage.textContent = message;
  lastActionChip.textContent = action;
}

function updateRequestIdChip(requestId) {
  lastRequestId = requestId;
  requestIdChip.textContent = `Request: ${requestId || "-"}`;
}

function makeHeaders(requestId) {
  const headers = { "Content-Type": "application/json" };
  if (requestId) {
    headers["X-Request-ID"] = requestId;
  }
  return headers;
}

function getResponseRequestId(response) {
  return response.headers.get("X-Request-ID") || lastRequestId;
}

function renderAuditItems(items) {
  if (!items.length) {
    auditList.innerHTML = "<div class=\"audit-item\">No audit events match these filters.</div>";
    return;
  }

  auditList.innerHTML = items
    .map((item) => {
      const requestId = item.details?.request_id || "-";
      const challengeId = item.details?.challenge_id || "-";
      return `
        <article class="audit-item">
          <div class="audit-head">
            <span class="audit-title">${item.action}</span>
            <span class="audit-status ${item.status}">${item.status}</span>
          </div>
          <p class="audit-meta">User: ${item.user_id || "-"} | Lab: ${item.lab_id || "-"}</p>
          <p class="audit-meta">Challenge: ${challengeId}</p>
          <p class="audit-meta">Request: ${requestId}</p>
          <p class="audit-meta">At: ${new Date(item.created_at).toLocaleString()}</p>
        </article>
      `;
    })
    .join("");
}

async function fetchAuditEvents() {
  const params = new URLSearchParams({
    limit: String(auditLimit),
    offset: String(auditOffset),
  });

  if (auditAction.value) {
    params.set("action", auditAction.value);
  }
  if (auditStatus.value) {
    params.set("status", auditStatus.value);
  }
  if (auditRequest.value.trim()) {
    params.set("request_id", auditRequest.value.trim());
  }

  const response = await fetch(`/api/v1/audit/events?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to load audit events: ${response.status}`);
  }

  const payload = await response.json();
  renderAuditItems(payload.items || []);

  const total = payload.total || 0;
  const start = Math.min(total, payload.offset + 1);
  const end = Math.min(total, payload.offset + payload.items.length);
  auditMeta.textContent = total
    ? `Showing ${start}-${end} of ${total} events`
    : "No events yet.";

  auditPrevBtn.disabled = payload.offset <= 0;
  auditNextBtn.disabled = payload.offset + payload.limit >= total;
}

async function fetchChallenges() {
  const response = await fetch("/api/v1/challenges");
  if (!response.ok) {
    throw new Error(`Failed to load challenges: ${response.status}`);
  }
  allContent = await response.json();
  rebuildFilterOptions();

  const filtered = applyContentFilters(allContent);

  challengeSelect.innerHTML = "";
  for (const challenge of filtered) {
    const option = document.createElement("option");
    option.value = challenge.id;
    const labelType = challenge.content_type === "killchain" ? "killchain" : "challenge";
    option.textContent = `${challenge.name} [${labelType}] (${challenge.id})`;
    challengeSelect.appendChild(option);
  }

  if (!filtered.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No content for selected type";
    challengeSelect.appendChild(option);
  }
}

async function fetchCatalogSummary() {
  const response = await fetch("/api/v1/catalog/summary");
  if (!response.ok) {
    throw new Error(`Failed to load summary: ${response.status}`);
  }
  const summary = await response.json();
  const content = summary.content || {};

  summaryChips.innerHTML = "";
  const chips = [
    `Independent: ${content.independent ?? 0}`,
    `Killchains: ${content.killchain ?? 0}`,
    `Total: ${content.total ?? 0}`,
  ];
  for (const label of chips) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = label;
    summaryChips.appendChild(chip);
  }
}

function setSessionState(session) {
  activeLabId = session?.id || null;
  resetBtn.disabled = !activeLabId;

  labIdEl.textContent = session?.id || "-";
  labStateEl.textContent = session?.state || "-";
  targetIpEl.textContent = session?.connection?.target_ip || "-";
  attackerIpEl.textContent = session?.connection?.attacker_ip || "-";

  rawPayload.textContent = session ? JSON.stringify(session, null, 2) : "No session yet.";
}

async function deployLab() {
  deployBtn.disabled = true;
  const requestId = nextRequestId();
  updateRequestIdChip(requestId);
  setFlash("Deploying lab...", "deploy");
  try {
    const response = await fetch("/api/v1/labs/deploy", {
      method: "POST",
      headers: makeHeaders(requestId),
      body: JSON.stringify({
        user_id: userIdInput.value.trim() || "student-01",
        challenge_id: challengeSelect.value,
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Deploy failed: ${detail}`);
    }

    const session = await response.json();
    setSessionState(session);
    updateRequestIdChip(getResponseRequestId(response));
    setFlash("Lab deployed successfully.", "deploy:success");
    await fetchAuditEvents();
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Deploy failed. Inspect payload details.", "deploy:failed");
  } finally {
    deployBtn.disabled = false;
  }
}

async function resetLab() {
  if (!activeLabId) {
    return;
  }

  resetBtn.disabled = true;
  const requestId = nextRequestId();
  updateRequestIdChip(requestId);
  setFlash("Resetting lab...", "reset");
  try {
    const response = await fetch(`/api/v1/labs/${activeLabId}/reset`, {
      method: "POST",
      headers: makeHeaders(requestId),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Reset failed: ${detail}`);
    }
    const session = await response.json();
    setSessionState(session);
    updateRequestIdChip(getResponseRequestId(response));
    setFlash("Lab reset completed.", "reset:success");
    await fetchAuditEvents();
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Reset failed. Inspect payload details.", "reset:failed");
  } finally {
    resetBtn.disabled = false;
  }
}

deployBtn.addEventListener("click", deployLab);
resetBtn.addEventListener("click", resetLab);
refreshBtn.addEventListener("click", async () => {
  try {
    await fetchChallenges();
    await fetchCatalogSummary();
    setFlash("Challenge catalog refreshed.", "refresh");
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Could not refresh challenges.", "refresh:failed");
  }
});

contentTypeSelect.addEventListener("change", async () => {
  try {
    await fetchChallenges();
    setFlash("Content filter updated.", "filter");
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Could not apply content filter.", "filter:failed");
  }
});

domainSelect.addEventListener("change", async () => {
  try {
    await fetchChallenges();
    setFlash("Domain filter updated.", "filter");
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Could not apply domain filter.", "filter:failed");
  }
});

difficultySelect.addEventListener("change", async () => {
  try {
    await fetchChallenges();
    setFlash("Difficulty filter updated.", "filter");
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Could not apply difficulty filter.", "filter:failed");
  }
});

auditApplyBtn.addEventListener("click", async () => {
  try {
    auditOffset = 0;
    await fetchAuditEvents();
    setFlash("Audit filters applied.", "audit");
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Could not load audit events.", "audit:failed");
  }
});

auditClearBtn.addEventListener("click", async () => {
  auditAction.value = "";
  auditStatus.value = "";
  auditRequest.value = "";
  auditOffset = 0;
  try {
    await fetchAuditEvents();
    setFlash("Audit filters cleared.", "audit");
  } catch (error) {
    rawPayload.textContent = String(error);
    setFlash("Could not load audit events.", "audit:failed");
  }
});

auditPrevBtn.addEventListener("click", async () => {
  auditOffset = Math.max(0, auditOffset - auditLimit);
  try {
    await fetchAuditEvents();
  } catch (error) {
    rawPayload.textContent = String(error);
  }
});

auditNextBtn.addEventListener("click", async () => {
  auditOffset += auditLimit;
  try {
    await fetchAuditEvents();
  } catch (error) {
    rawPayload.textContent = String(error);
  }
});

fetchChallenges().catch((error) => {
  rawPayload.textContent = String(error);
  setFlash("Could not load challenge catalog.", "boot:failed");
});

fetchCatalogSummary().catch((error) => {
  rawPayload.textContent = String(error);
  setFlash("Could not load catalog summary.", "boot:failed");
});

fetchAuditEvents().catch((error) => {
  rawPayload.textContent = String(error);
  setFlash("Could not load audit events.", "boot:failed");
});

themeToggle.addEventListener("change", () => {
  applyTheme(themeToggle.checked ? "dark" : "light");
});

initTheme();
