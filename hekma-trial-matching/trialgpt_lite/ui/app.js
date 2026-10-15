// Clinical presets
const PRESETS = {
  nsclc: {
    condition: "non-small cell lung cancer",
    age: 58,
    sex: "FEMALE",
    location: "Boston, MA",
  },
  tnbc: {
    condition: "triple negative breast cancer",
    age: 45,
    sex: "FEMALE",
    location: "New York, NY",
  },
  melanoma: {
    condition: "melanoma",
    age: 62,
    sex: "MALE",
    location: "San Francisco, CA",
  },
  diabetes: {
    condition: "type 2 diabetes",
    age: 54,
    sex: "MALE",
    location: "Chicago, IL",
  },
};

let currentTrials = [];
let activeFilter = "ALL";
let currentSearchTerm = "";
let currentActiveView = "matcher"; // "matcher" or "monitor"
let currentMonitorSubtab = "new"; // "new", "updated", "history"
let cachedRegistryMetrics = null;

// Search target flow: "myself" vs "friend"
let currentSearchTarget = "myself";

// Interactive Eligibility Screener state
let currentActiveQuestNctId = null;
let currentQuestData = null;
let userQuestAnswers = {}; // { [criterion_index]: 'yes' | 'no' | 'unsure' }
let wizardCurrentStep = 0;
let wizardAutoAdvanceTimer = null;

// Pagination state (top 10 per page with forward/back navigation)
let currentQueryPayload = null;
let pageTokensStack = [null]; // pageTokensStack[0] is null (page 1)
let currentPageIndex = 0;
let currentNextPageToken = null;

// Theme handling
function initTheme() {
  const savedTheme = localStorage.getItem("trialgpt_theme") || "light";
  document.documentElement.setAttribute("data-theme", savedTheme);
  updateThemeButton(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const target = current === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", target);
  localStorage.setItem("trialgpt_theme", target);
  updateThemeButton(target);
}

function updateThemeButton(theme) {
  const icon = document.getElementById("theme-icon");
  const label = document.getElementById("theme-label");
  if (!icon || !label) return;
  if (theme === "dark") {
    icon.textContent = "☀️";
    label.textContent = "Light";
  } else {
    icon.textContent = "🌙";
    label.textContent = "Dark";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  // Silently preload registry metrics on page load
  loadRegistryMetrics(false);

  // Auto-refresh registry metrics every 3 minutes while the page is open
  setInterval(() => {
    if (currentActiveView === "monitor") {
      loadRegistryMetrics(false);
    }
  }, 180000);
});

// View Switcher: Matcher vs Registry Monitor
function switchView(view) {
  currentActiveView = view;
  const matcherView = document.getElementById("view-matcher");
  const monitorView = document.getElementById("view-monitor");
  const tabMatcher = document.getElementById("tab-nav-matcher");
  const tabMonitor = document.getElementById("tab-nav-monitor");

  if (view === "monitor") {
    matcherView.style.display = "none";
    monitorView.style.display = "flex";
    tabMonitor.classList.add("active");
    tabMatcher.classList.remove("active");
    if (!cachedRegistryMetrics) {
      loadRegistryMetrics(false);
    }
    loadRegistryFeed();
  } else {
    monitorView.style.display = "none";
    matcherView.style.display = "grid";
    tabMatcher.classList.add("active");
    tabMonitor.classList.remove("active");
  }
}

// Switch search target flow: 'myself' vs 'friend'
function switchSearchTarget(target) {
  currentSearchTarget = target;
  const btnMyself = document.getElementById("tab-btn-myself");
  const btnFriend = document.getElementById("tab-btn-friend");
  const profileBox = document.getElementById("profile-prefill-box");
  const friendGrid = document.getElementById("friend-demographics-grid");

  if (target === "myself") {
    btnMyself?.classList.add("active");
    btnFriend?.classList.remove("active");
    if (profileBox) profileBox.style.display = "flex";
    if (friendGrid) friendGrid.style.display = "none";
  } else {
    btnMyself?.classList.remove("active");
    btnFriend?.classList.add("active");
    if (profileBox) profileBox.style.display = "none";
    if (friendGrid) friendGrid.style.display = "grid";
  }
}

// Client-side Geo Resolver for city or postal code
function resolveGeoLocation(locStr) {
  const s = (locStr || "").trim().toLowerCase();
  if (!s) return null;

  // Check if comma-separated lat,lon was directly entered (e.g., "42.36, -71.05")
  const latLonMatch = s.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
  if (latLonMatch) {
    return { lat: parseFloat(latLonMatch[1]), lon: parseFloat(latLonMatch[2]) };
  }

  const KNOWN_GEO = {
    // Boston & MA
    "boston": { lat: 42.3601, lon: -71.0589 },
    "02115": { lat: 42.3398, lon: -71.1017 },
    "02114": { lat: 42.3627, lon: -71.0691 },
    "cambridge": { lat: 42.3736, lon: -71.1097 },
    // New York & NY
    "new york": { lat: 40.7128, lon: -74.0060 },
    "nyc": { lat: 40.7128, lon: -74.0060 },
    "10001": { lat: 40.7501, lon: -73.9996 },
    "10065": { lat: 40.7648, lon: -73.9634 },
    // San Francisco & Bay Area
    "san francisco": { lat: 37.7749, lon: -122.4194 },
    "sf": { lat: 37.7749, lon: -122.4194 },
    "94102": { lat: 37.7776, lon: -122.4199 },
    "94143": { lat: 37.7631, lon: -122.4578 },
    // Houston
    "houston": { lat: 29.7604, lon: -95.3698 },
    "77030": { lat: 29.7108, lon: -95.3977 },
    // Chicago
    "chicago": { lat: 41.8781, lon: -87.6298 },
    "60611": { lat: 41.8986, lon: -87.6202 },
    // Los Angeles
    "los angeles": { lat: 34.0522, lon: -118.2437 },
    "la": { lat: 34.0522, lon: -118.2437 },
    "90095": { lat: 34.0689, lon: -118.4452 },
    // Philadelphia
    "philadelphia": { lat: 39.9526, lon: -75.1652 },
    "19104": { lat: 39.9566, lon: -75.2014 },
    // Seattle
    "seattle": { lat: 47.6062, lon: -122.3321 },
    "98109": { lat: 47.6322, lon: -122.3486 },
  };

  for (const [key, coords] of Object.entries(KNOWN_GEO)) {
    if (s.includes(key)) {
      return coords;
    }
  }

  // Fallback default
  return { lat: 42.3601, lon: -71.0589 };
}

function loadPreset(key) {
  const preset = PRESETS[key];
  if (!preset) return;

  const condEl = document.getElementById("condition-input");
  if (condEl) condEl.value = preset.condition;

  const locEl = document.getElementById("location-input");
  if (locEl && preset.location) locEl.value = preset.location;

  const ageEl = document.getElementById("age-input");
  if (ageEl) ageEl.value = preset.age;

  const sexEl = document.getElementById("sex-select");
  if (sexEl) sexEl.value = preset.sex;
}

function resetForm() {
  const form = document.getElementById("match-form");
  if (form) form.reset();
  switchSearchTarget("myself");
  const locInput = document.getElementById("location-input");
  if (locInput) locInput.value = "Boston, MA";
  const radSelect = document.getElementById("radius-select");
  if (radSelect) radSelect.value = "30";

  document.getElementById("metrics-grid").style.display = "none";
  document.getElementById("results-toolbar").style.display = "none";
  document.getElementById("trials-feed").innerHTML = `
    <div class="welcome-hero" id="welcome-hero">
      <div class="hero-header">
        <h3>Clinical Trial Intelligence</h3>
        <p>Direct real-time retrieval from the official ClinicalTrials.gov REST API v2 with automated eligibility evaluation.</p>
      </div>

      <div class="feature-cards-grid">
        <div class="feature-card">
          <div class="feat-icon">1</div>
          <h4>Direct Registry Integration</h4>
          <p>Queries official ClinicalTrials.gov REST API v2 endpoints with automatic query relaxation and retry resilience.</p>
        </div>
        <div class="feature-card">
          <div class="feat-icon">2</div>
          <h4>Two-Tier Pre-Screening</h4>
          <p>Instantly screens demographic boundaries (age, biological sex) before running deeper criteria analysis.</p>
        </div>
        <div class="feature-card">
          <div class="feat-icon">3</div>
          <h4>Evidence Attribution</h4>
          <p>Cites exact patient sentences and delivers explainable verdicts: Eligible, Likely Eligible, or Ineligible.</p>
        </div>
      </div>
    </div>
  `;
}

function updateSentenceCount() {
  // Legacy handler kept for compatibility
}

async function handleMatch(e) {
  if (e) e.preventDefault();

  const condition = document.getElementById("condition-input").value.trim();
  if (!condition) {
    alert("Please enter a target medical condition.");
    return;
  }

  const maxTrials = parseInt(document.getElementById("max-trials-input")?.value) || 10;
  const recruitingOnly = document.getElementById("recruiting-only-checkbox")?.checked ?? true;

  // Resolve Geo-filtering
  const locVal = document.getElementById("location-input")?.value?.trim() || "";
  const radiusVal = parseInt(document.getElementById("radius-select")?.value) || 30;
  let geoFilter = null;
  if (locVal) {
    const coords = resolveGeoLocation(locVal);
    if (coords) {
      geoFilter = {
        city_or_zip: locVal,
        latitude: coords.lat,
        longitude: coords.lon,
        distance_miles: radiusVal,
      };
    } else {
      geoFilter = {
        city_or_zip: locVal,
        distance_miles: radiusVal,
      };
    }
  }

  // Demographics based on target flow
  let demographics = null;
  if (currentSearchTarget === "myself") {
    // Flow 1: Profile defaults (Age 52, Female)
    demographics = {
      age: 52,
      sex: "FEMALE",
    };
  } else {
    // Flow 2: Friend Demographics
    const friendAge = document.getElementById("age-input")?.value;
    const friendSex = document.getElementById("sex-select")?.value;
    demographics = {
      age: friendAge ? parseFloat(friendAge) : null,
      sex: (friendSex && friendSex !== "ALL") ? friendSex : null,
    };
  }

  // Build the reusable query payload for pagination (top 10 results per page)
  currentQueryPayload = {
    condition,
    city_or_zip: locVal || null,
    search_radius_miles: locVal ? radiusVal : null,
    page_size: maxTrials || 10,
    recruiting_only: recruitingOnly,
    geo_filter: geoFilter,
    demographics: (demographics && (demographics.age || demographics.sex)) ? demographics : null,
  };

  // Reset pagination state for a new search
  pageTokensStack = [null];
  currentPageIndex = 0;
  currentNextPageToken = null;

  await executeQueryPage(null);
}

async function executeQueryPage(pageToken) {
  if (!currentQueryPayload) return;

  const submitBtn = document.getElementById("submit-btn");
  const loadingBox = document.getElementById("loading-box");
  const welcomeHero = document.getElementById("welcome-hero");
  const trialsFeed = document.getElementById("trials-feed");
  const loadingTitle = document.getElementById("loading-title");
  const loadingSubtitle = document.getElementById("loading-subtitle");
  const paginationContainer = document.getElementById("pagination-container");

  if (submitBtn) submitBtn.disabled = true;
  if (welcomeHero) welcomeHero.style.display = "none";
  if (paginationContainer) paginationContainer.style.display = "none";
  if (loadingBox) loadingBox.style.display = "flex";
  if (trialsFeed) trialsFeed.innerHTML = "";

  const pageNum = currentPageIndex + 1;
  const targetLabel = currentSearchTarget === "myself" ? "Profile (Age 52, Female)" : "Friend Demographics";
  const geoLabel = currentQueryPayload.geo_filter ? ` | Within ${currentQueryPayload.geo_filter.distance_miles}mi` : "";

  loadingTitle.textContent = `Querying ClinicalTrials.gov REST API v2 (Page ${pageNum})...`;
  loadingSubtitle.textContent = `Fetching trials for '${currentQueryPayload.condition}' [${targetLabel}${geoLabel}]`;

  const payload = {
    ...currentQueryPayload,
    page_token: pageToken || null,
  };

  try {
    const res = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || err.message || "Query failed");
    }

    const report = await res.json();
    currentNextPageToken = report.next_page_token || null;
    displayResults(report);
  } catch (error) {
    alert(`Error: ${error.message}`);
    if (welcomeHero && (!currentTrials || currentTrials.length === 0)) {
      welcomeHero.style.display = "flex";
    }
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (loadingBox) loadingBox.style.display = "none";
  }
}

async function loadNextPage() {
  if (!currentNextPageToken) return;

  // Add next page token to stack if not already there
  if (pageTokensStack.length <= currentPageIndex + 1) {
    pageTokensStack.push(currentNextPageToken);
  }
  currentPageIndex++;
  await executeQueryPage(pageTokensStack[currentPageIndex]);

  // Scroll smoothly to results toolbar
  document.getElementById("results-toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadPreviousPage() {
  if (currentPageIndex <= 0) return;

  currentPageIndex--;
  await executeQueryPage(pageTokensStack[currentPageIndex]);

  // Scroll smoothly to results toolbar
  document.getElementById("results-toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function updatePaginationControls(report) {
  const container = document.getElementById("pagination-container");
  if (!container) return;
  if (!currentTrials || currentTrials.length === 0) {
    container.style.display = "none";
    return;
  }
  container.style.display = "flex";

  const pageSize = report.page_size || 10;
  const startIdx = currentPageIndex * pageSize + 1;
  const endIdx = startIdx + currentTrials.length - 1;
  const total = report.total_trials_in_registry || 0;

  const infoEl = document.getElementById("pagination-info");
  if (infoEl) {
    infoEl.innerHTML = `Showing <strong>${startIdx}–${endIdx}</strong> of <strong>${total.toLocaleString()}</strong> studies in registry`;
  }

  const pageBadge = document.getElementById("current-page-badge");
  if (pageBadge) {
    pageBadge.textContent = `Page ${currentPageIndex + 1}`;
  }

  const prevBtn = document.getElementById("btn-prev-page");
  if (prevBtn) {
    prevBtn.disabled = (currentPageIndex === 0);
  }

  const nextBtn = document.getElementById("btn-next-page");
  if (nextBtn) {
    nextBtn.disabled = !currentNextPageToken;
    nextBtn.innerHTML = currentNextPageToken 
      ? `<span>Next 10 Studies ➔</span>` 
      : `<span>No More Pages</span>`;
  }
}

function displayResults(report) {
  currentTrials = report.trials || [];
  currentSearchTerm = "";
  activeFilter = "ALL";

  const withinInput = document.getElementById("search-within-input");
  if (withinInput) withinInput.value = "";

  // Metrics
  document.getElementById("metrics-grid").style.display = "grid";
  document.getElementById("metric-total").textContent = (report.total_trials_in_registry || 0).toLocaleString();
  document.getElementById("metric-fetched").textContent = report.retrieved_trials_count || 0;
  const latencyEl = document.getElementById("metric-latency");
  if (latencyEl) {
    if (report.cache_hit) {
      latencyEl.innerHTML = `${report.execution_time_seconds}s <span style="font-size:0.65rem; background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); border-radius:4px; padding:2px 6px; margin-left:4px; font-weight:600;">⚡ CACHED</span>`;
    } else {
      latencyEl.textContent = `${report.execution_time_seconds}s`;
    }
  }


  // Toolbar
  document.getElementById("results-toolbar").style.display = "flex";
  
  updateFilterPills(report.evaluated_trials_count === 0);
  renderCards();
  updatePaginationControls(report);
}

function updateFilterPills(isConditionOnly = false) {
  const filterGroup = document.querySelector(".filter-group");
  if (!filterGroup || !currentTrials) return;

  const eligibleCount = currentTrials.filter(t => t.verdict === "ELIGIBLE").length;
  const likelyCount = currentTrials.filter(t => t.verdict === "LIKELY_ELIGIBLE").length;
  const ineligibleCount = currentTrials.filter(t => t.verdict === "INELIGIBLE").length;
  const hasEvaluated = eligibleCount > 0 || likelyCount > 0 || ineligibleCount > 0;

  if (isConditionOnly && !hasEvaluated) {
    filterGroup.innerHTML = `
      <button type="button" class="filter-pill active" onclick="setTabFilter('ALL', this)">
        All Retrieved (${currentTrials.length})
      </button>
    `;
  } else {
    filterGroup.innerHTML = `
      <button type="button" class="filter-pill ${activeFilter === 'ALL' ? 'active' : ''}" onclick="setTabFilter('ALL', this)">
        All (${currentTrials.length})
      </button>
      <button type="button" class="filter-pill ${activeFilter === 'ELIGIBLE' ? 'active' : ''}" onclick="setTabFilter('ELIGIBLE', this)">
        Eligible (${eligibleCount})
      </button>
      <button type="button" class="filter-pill ${activeFilter === 'LIKELY_ELIGIBLE' ? 'active' : ''}" onclick="setTabFilter('LIKELY_ELIGIBLE', this)">
        Likely (${likelyCount})
      </button>
      <button type="button" class="filter-pill ${activeFilter === 'INELIGIBLE' ? 'active' : ''}" onclick="setTabFilter('INELIGIBLE', this)">
        Ineligible (${ineligibleCount})
      </button>
    `;
  }
}

function setTabFilter(filter, el) {
  activeFilter = filter;
  document.querySelectorAll(".filter-pill").forEach(tab => tab.classList.remove("active"));
  if (el) el.classList.add("active");
  renderCards();
}

function handleSearchWithin(query) {
  currentSearchTerm = query.trim().toLowerCase();
  renderCards();
}

function renderCards() {
  const container = document.getElementById("trials-feed");
  
  let filtered = activeFilter === "ALL" 
    ? currentTrials 
    : currentTrials.filter(t => t.verdict === activeFilter);

  if (currentSearchTerm) {
    filtered = filtered.filter(t => {
      const titleMatch = (t.title || "").toLowerCase().includes(currentSearchTerm);
      const nctMatch = (t.nct_id || "").toLowerCase().includes(currentSearchTerm);
      const drugMatch = (t.interventions || []).some(i => i.toLowerCase().includes(currentSearchTerm));
      return titleMatch || nctMatch || drugMatch;
    });
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="background: var(--bg-surface); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 3rem 2rem; text-align: center;">
        <h4 style="font-weight: 600; color: var(--text-main);">No matching studies</h4>
        <p style="font-size: 0.825rem; color: var(--text-subtle); margin-top: 0.25rem;">Try clearing your filter or modifying search terms.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map((trial, index) => {
    const drawerId = `drawer-${index}`;

    let calloutClass = "callout-default";
    let displayVerdict = (trial.verdict || "RETRIEVED_ONLY").replace(/_/g, " ");

    if (trial.verdict === "INELIGIBLE") {
      calloutClass = "callout-ineligible";
    } else if (trial.verdict === "ELIGIBLE") {
      calloutClass = "callout-eligible";
    } else if (trial.verdict === "LIKELY_ELIGIBLE") {
      calloutClass = "callout-likely";
    } else if (trial.verdict === "RETRIEVED_ONLY") {
      displayVerdict = "ACTIVE";
    }

    const conditionsStr = trial.conditions && trial.conditions.length ? trial.conditions.join(", ") : "Not specified";
    const phaseStr = trial.phases && trial.phases.length ? trial.phases.join(", ") : "Phase N/A";
    const studyType = trial.study_type || "INTERVENTIONAL";
    const nctLink = trial.web_url || `https://clinicaltrials.gov/study/${trial.nct_id}`;

    return `
      <article class="trial-entry" id="trial-card-${trial.nct_id}">
        <!-- Header: NCT ID, Recruitment Status, Phase, Study Type, Match Status Verdict -->
        <div class="entry-header">
          <div class="entry-tags">
            <a href="${nctLink}" target="_blank" rel="noopener noreferrer" class="nct-link" title="Open ClinicalTrials.gov record">
              ${trial.nct_id} ↗
            </a>
            <button type="button" class="btn-copy-chip" onclick="copyNCT('${trial.nct_id}', this)" title="Copy NCT ID">Copy</button>
            <span class="status-chip" title="Recruitment Status">${escapeHtml(trial.overall_status || "UNKNOWN")}</span>
            <span class="study-type-chip" title="Study Type">${escapeHtml(studyType)}</span>
            <span class="phase-chip" title="Study Phase">${escapeHtml(phaseStr)}</span>
          </div>
          <div class="verdict-tag ${trial.verdict}" title="Match Status">
            ${escapeHtml(displayVerdict)}
          </div>
        </div>

        <!-- Trial Title -->
        <h3 class="trial-name">${escapeHtml(trial.title)}</h3>

        <!-- Match Status / Reasons Callout -->
        <div class="verdict-callout ${calloutClass}">
          <div style="font-weight: 700; margin-bottom: 0.2rem; display: flex; align-items: center; gap: 0.4rem;">
            <span>Match Status: ${escapeHtml(displayVerdict)}</span>
            ${trial.eligibility_score ? `<span style="font-size: 0.72rem; opacity: 0.85; font-weight: 500;">(Score: ${(trial.eligibility_score * 100).toFixed(0)}%)</span>` : ""}
          </div>
          <div>${escapeHtml(trial.summary_reasoning || "Study matches inclusion criteria.")}</div>
        </div>

        <!-- Primary Output Fields Grid: Condition, Age, Sex, Location -->
        <div class="trial-primary-specs">
          <div class="spec-cell">
            <span class="spec-label">Condition</span>
            <span class="spec-val" title="${escapeHtml(conditionsStr)}">${escapeHtml(conditionsStr)}</span>
          </div>
          <div class="spec-cell">
            <span class="spec-label">Age Requirement</span>
            <span class="spec-val">${escapeHtml(trial.age_display || "All Ages")}</span>
          </div>
          <div class="spec-cell">
            <span class="spec-label">Sex Restriction</span>
            <span class="spec-val">${escapeHtml(trial.sex_display || "All / Both")}</span>
          </div>
          <div class="spec-cell">
            <span class="spec-label">Primary Location / Site</span>
            <span class="spec-val" title="${escapeHtml(trial.location_display || "Location not listed")}">${escapeHtml(trial.location_display || "Location not listed")}</span>
          </div>
        </div>

        <!-- Intervention Chips -->
        ${trial.interventions && trial.interventions.length ? `
          <div class="drug-chips">
            ${trial.interventions.slice(0, 4).map(i => `<span class="drug-chip">${escapeHtml(i)}</span>`).join("")}
            ${trial.interventions.length > 4 ? `<span class="drug-chip" style="background: var(--bg-surface); color: var(--text-subtle);">+${trial.interventions.length - 4} more</span>` : ""}
          </div>
        ` : ""}

        <!-- Quick Contacts Banner (if present) -->
        ${trial.contacts && (trial.contacts.central_contacts?.length || trial.contacts.overall_officials?.length) ? `
          <div class="trial-contacts-box">
            ${trial.contacts.central_contacts?.length ? `
              <div class="contact-item">
                <span class="contact-label">📞 Contact:</span>
                <span class="contact-val">
                  <strong>${escapeHtml(trial.contacts.central_contacts[0].name || "Study Contact")}</strong>
                  ${trial.contacts.central_contacts[0].phone ? `• <a href="tel:${escapeHtml(trial.contacts.central_contacts[0].phone)}">${escapeHtml(trial.contacts.central_contacts[0].phone)}</a>` : ""}
                  ${trial.contacts.central_contacts[0].email ? `• <a href="mailto:${escapeHtml(trial.contacts.central_contacts[0].email)}">${escapeHtml(trial.contacts.central_contacts[0].email)}</a>` : ""}
                </span>
              </div>
            ` : ""}
            ${trial.contacts.overall_officials?.length ? `
              <div class="contact-item">
                <span class="contact-label">👨‍⚕️ Investigator:</span>
                <span class="contact-val">
                  ${escapeHtml(trial.contacts.overall_officials[0].name || "")}
                  ${trial.contacts.overall_officials[0].affiliation ? `(${escapeHtml(trial.contacts.overall_officials[0].affiliation)})` : ""}
                </span>
              </div>
            ` : ""}
          </div>
        ` : ""}

        <!-- Action Buttons Row: Screener + Plain-English Summary -->
        <div style="display: grid; grid-template-columns: 1.15fr 0.95fr; gap: 0.5rem; margin-top: 0.65rem; margin-bottom: 0.35rem;">
          <button type="button" class="btn-check-eligibility ${trial._is_self_screened ? 'screened' : ''}" onclick="openEligibilityQuestionnaire('${trial.nct_id}', '${escapeAttr(trial.title)}')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
            <span>${trial._is_self_screened ? `✓ Self-Screened (${(trial.eligibility_score * 100).toFixed(0)}%)` : "See If I'm Eligible"}</span>
          </button>
          <button type="button" class="btn-patient-summary" onclick="openPatientSummaryModal('${trial.nct_id}', '${escapeAttr(trial.title)}')">
            <span>📖 Plain-English Summary</span>
          </button>
        </div>

        <!-- More Details Button -->
        <div style="margin-top: 0.25rem;">
          <button type="button" class="btn-protocol-expand" onclick="toggleDetails('${drawerId}', '${trial.nct_id}')">
            <span style="display: inline-flex; align-items: center; gap: 0.5rem;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              <span>📋 View Complete Protocol Details & Sections (14 Sections)</span>
            </span>
            <span id="${drawerId}-arrow" style="font-weight: 700;">Expand ▾</span>
          </button>
        </div>

        <!-- Detailed Multi-Section Protocol Breakdown Drawer -->
        <div id="${drawerId}" class="protocol-details-drawer" style="display: none;">
          <!-- 1. Overview -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/></svg>
              <span>1. Overview (Brief Summary)</span>
            </div>
            <div class="pdetail-card-body">
              ${escapeHtml(trial.brief_summary || "No brief summary provided by study sponsor.")}
            </div>
          </div>

          <!-- 2. Condition -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              <span>2. Condition (Disease / Condition)</span>
            </div>
            <div class="pdetail-card-body">
              ${trial.conditions && trial.conditions.length ? `
                <div style="display: flex; flex-wrap: wrap; gap: 0.35rem;">
                  ${trial.conditions.map(c => `<span class="drug-chip" style="background: rgba(14, 165, 233, 0.08); color: #0284C7; border: 1px solid rgba(14, 165, 233, 0.2);">${escapeHtml(c)}</span>`).join("")}
                </div>
              ` : `<span style="color: var(--text-subtle);">None specified</span>`}
            </div>
          </div>

          <!-- 3. Treatment -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
              <span>3. Treatment (Intervention Details)</span>
            </div>
            <div class="pdetail-card-body">
              ${trial.detailed_interventions && trial.detailed_interventions.length ? `
                <table class="interventions-table">
                  <thead>
                    <tr>
                      <th style="width: 25%;">Intervention Type</th>
                      <th style="width: 35%;">Name</th>
                      <th style="width: 40%;">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${trial.detailed_interventions.map(it => `
                      <tr>
                        <td><strong>${escapeHtml(it.type || "OTHER")}</strong></td>
                        <td>${escapeHtml(it.name || "N/A")}</td>
                        <td style="color: var(--text-muted); font-size: 0.775rem;">${escapeHtml(it.description || "—")}</td>
                      </tr>
                    `).join("")}
                  </tbody>
                </table>
              ` : (trial.interventions && trial.interventions.length ? `
                <div style="display: flex; flex-wrap: wrap; gap: 0.35rem;">
                  ${trial.interventions.map(i => `<span class="drug-chip">${escapeHtml(i)}</span>`).join("")}
                </div>
              ` : `<span style="color: var(--text-subtle);">No intervention details provided.</span>`)}
            </div>
          </div>

          <!-- 4. Participation Criteria -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              <span>4. Participation Criteria (Inclusion / Exclusion)</span>
            </div>
            <div class="pdetail-card-body">
              ${renderParticipationCriteria(trial)}
            </div>
          </div>

          <!-- 5. Age/Sex -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              <span>5. Age & Sex (Eligibility Demographics)</span>
            </div>
            <div class="pdetail-card-body">
              <div class="pdetail-grid">
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Minimum Age</span>
                  <span class="pdetail-kv-val">${escapeHtml(formatAgeBound(trial.demographics?.minimum_age_years, trial.demographics?.minimum_age_text))}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Maximum Age</span>
                  <span class="pdetail-kv-val">${escapeHtml(formatAgeBound(trial.demographics?.maximum_age_years, trial.demographics?.maximum_age_text))}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Sex Restriction</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.sex_display || trial.demographics?.sex || "All / Both")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Healthy Volunteers</span>
                  <span class="pdetail-kv-val">${escapeHtml(formatHealthyVolunteers(trial.demographics))}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 6. Study Design -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
              <span>6. Study Design (Randomized, Masking, Allocation)</span>
            </div>
            <div class="pdetail-card-body">
              <div class="pdetail-grid">
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Allocation</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.design?.allocation || "Not Applicable")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Intervention Model</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.design?.intervention_model || "Not Specified")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Masking</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.design?.masking || "None (Open Label)")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Primary Purpose</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.design?.primary_purpose || "Treatment")}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 7. Phase -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              <span>7. Phase</span>
            </div>
            <div class="pdetail-card-body">
              <div class="pdetail-grid">
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Phase</span>
                  <span class="pdetail-kv-val">${escapeHtml(phaseStr)}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Study Type</span>
                  <span class="pdetail-kv-val">${escapeHtml(studyType)}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 8. Enrollment -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              <span>8. Enrollment (Planned Enrollment)</span>
            </div>
            <div class="pdetail-card-body">
              <div class="pdetail-grid">
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Target Enrollment</span>
                  <span class="pdetail-kv-val">${trial.enrollment?.count ? trial.enrollment.count.toLocaleString() + " participants" : "Not Specified"}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Enrollment Type</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.enrollment?.type || "Anticipated")}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 9. Sponsor -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              <span>9. Sponsor (Lead Sponsor & Collaborators)</span>
            </div>
            <div class="pdetail-card-body">
              <div class="pdetail-grid">
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Lead Sponsor</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.lead_sponsor || "Not Listed")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Collaborators</span>
                  <span class="pdetail-kv-val">${trial.collaborators && trial.collaborators.length ? escapeHtml(trial.collaborators.join(", ")) : "None Listed"}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 10. Locations -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              <span>10. Locations (${trial.locations?.length || 0} Facilities / Cities / Countries)</span>
            </div>
            <div class="pdetail-card-body">
              ${trial.locations && trial.locations.length ? `
                <div style="max-height: 220px; overflow-y: auto; border: 1px solid var(--border-light); border-radius: var(--radius-sm);">
                  <table class="interventions-table" style="margin-top: 0;">
                    <thead>
                      <tr>
                        <th>Facility / Site</th>
                        <th>City</th>
                        <th>State / Region</th>
                        <th>Country</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${trial.locations.map(loc => `
                        <tr>
                          <td><strong>${escapeHtml(loc.facility || "Site")}</strong></td>
                          <td>${escapeHtml(loc.city || "—")}</td>
                          <td>${escapeHtml(loc.state || "—")}</td>
                          <td>${escapeHtml(loc.country || "—")}</td>
                          <td><span class="status-chip" style="font-size: 0.65rem;">${escapeHtml(loc.status || trial.overall_status)}</span></td>
                        </tr>
                      `).join("")}
                    </tbody>
                  </table>
                </div>
              ` : `<span style="color: var(--text-subtle);">No specific site locations provided.</span>`}
            </div>
          </div>

          <!-- 11. Timeline -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              <span>11. Timeline (Start & Completion Dates)</span>
            </div>
            <div class="pdetail-card-body">
              <div class="pdetail-grid">
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Study Start Date</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.timeline?.start_date || "Not Specified")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Primary Completion</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.timeline?.primary_completion_date || "Not Specified")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">Study Completion</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.timeline?.completion_date || "Not Specified")}</span>
                </div>
                <div class="pdetail-kv">
                  <span class="pdetail-kv-label">First Posted</span>
                  <span class="pdetail-kv-val">${escapeHtml(trial.timeline?.first_posted_date || "Not Specified")}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 12. Outcomes -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              <span>12. Outcomes (Primary & Secondary Outcomes)</span>
            </div>
            <div class="pdetail-card-body">
              ${(trial.primary_outcomes?.length || trial.secondary_outcomes?.length) ? `
                <div class="outcomes-list">
                  ${trial.primary_outcomes?.map(o => `
                    <div class="outcome-item">
                      <div class="outcome-measure"><span style="color: var(--primary); font-weight: 700; text-transform: uppercase; font-size: 0.675rem; letter-spacing: 0.05em; display: block; margin-bottom: 2px;">Primary Outcome</span> ${escapeHtml(o.measure)}</div>
                      ${o.time_frame ? `<div class="outcome-meta"><strong>Time Frame:</strong> ${escapeHtml(o.time_frame)}</div>` : ""}
                      ${o.description ? `<div class="outcome-meta" style="margin-top: 3px;">${escapeHtml(o.description)}</div>` : ""}
                    </div>
                  `).join("") || ""}
                  ${trial.secondary_outcomes?.map(o => `
                    <div class="outcome-item" style="border-left-color: #64748B;">
                      <div class="outcome-measure"><span style="color: #64748B; font-weight: 700; text-transform: uppercase; font-size: 0.675rem; letter-spacing: 0.05em; display: block; margin-bottom: 2px;">Secondary Outcome</span> ${escapeHtml(o.measure)}</div>
                      ${o.time_frame ? `<div class="outcome-meta"><strong>Time Frame:</strong> ${escapeHtml(o.time_frame)}</div>` : ""}
                      ${o.description ? `<div class="outcome-meta" style="margin-top: 3px;">${escapeHtml(o.description)}</div>` : ""}
                    </div>
                  `).join("") || ""}
                </div>
              ` : `<span style="color: var(--text-subtle);">No primary or secondary outcomes specified.</span>`}
            </div>
          </div>

          <!-- 13. Contact -->
          <div class="pdetail-card">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
              <span>13. Contact (Study Contacts & Investigators)</span>
            </div>
            <div class="pdetail-card-body">
              ${trial.contacts && (trial.contacts.central_contacts?.length || trial.contacts.overall_officials?.length) ? `
                <div class="pdetail-grid">
                  ${trial.contacts.central_contacts?.map(c => `
                    <div class="pdetail-kv">
                      <span class="pdetail-kv-label">Central Study Contact</span>
                      <span class="pdetail-kv-val">${escapeHtml(c.name || "Contact Person")}</span>
                      ${c.phone ? `<span style="font-size: 0.775rem; color: var(--primary);">📞 <a href="tel:${escapeHtml(c.phone)}">${escapeHtml(c.phone)}</a></span>` : ""}
                      ${c.email ? `<span style="font-size: 0.775rem; color: var(--primary);">✉️ <a href="mailto:${escapeHtml(c.email)}">${escapeHtml(c.email)}</a></span>` : ""}
                    </div>
                  `).join("") || ""}
                  ${trial.contacts.overall_officials?.map(off => `
                    <div class="pdetail-kv">
                      <span class="pdetail-kv-label">Investigator (${escapeHtml(off.role || "Official")})</span>
                      <span class="pdetail-kv-val">${escapeHtml(off.name || "Official")}</span>
                      ${off.affiliation ? `<span style="font-size: 0.75rem; color: var(--text-subtle);">${escapeHtml(off.affiliation)}</span>` : ""}
                    </div>
                  `).join("") || ""}
                </div>
              ` : `<span style="color: var(--text-subtle);">No direct study contact information published in public record.</span>`}
            </div>
          </div>

          <!-- 14. ClinicalTrials.gov -->
          <div class="pdetail-card" style="border-bottom: none;">
            <div class="pdetail-card-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
              <span>14. ClinicalTrials.gov (NCT Direct Link)</span>
            </div>
            <div class="pdetail-card-body" style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
              <a href="${nctLink}" target="_blank" rel="noopener noreferrer" class="btn-nct-external">
                <span>Open Official Trial Record (${trial.nct_id}) on ClinicalTrials.gov ↗</span>
              </a>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-family: 'JetBrains Mono', monospace;">${escapeHtml(nctLink)}</span>
            </div>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

function toggleDetails(id, nctId) {
  const drawer = document.getElementById(id);
  const arrow = document.getElementById(`${id}-arrow`);
  if (!drawer) return;

  const isHidden = drawer.style.display === "none";
  drawer.style.display = isHidden ? "flex" : "none";
  if (arrow) {
    arrow.textContent = isHidden ? "Collapse ▴" : "Expand ▾";
  }
  if (isHidden && nctId) {
    ensureParticipationCriteria(nctId, drawer);
  }
}

function participationCriteriaAreEmpty(protocol) {
  const criteria = protocol || {};
  return !(
    (criteria.inclusion_criteria && criteria.inclusion_criteria.length)
    || (criteria.exclusion_criteria && criteria.exclusion_criteria.length)
    || (criteria.raw_text || "").trim()
  );
}

async function ensureParticipationCriteria(nctId, drawer) {
  const trial = currentTrials.find((item) => item.nct_id === nctId);
  if (!trial || !participationCriteriaAreEmpty(trial.participation_criteria)) {
    return;
  }

  const section = [...drawer.querySelectorAll(".pdetail-card")].find((card) =>
    (card.querySelector(".pdetail-card-head")?.textContent || "").includes("Participation Criteria")
  );
  const body = section?.querySelector(".pdetail-card-body");
  if (body) {
    body.innerHTML = `<span style="color: var(--text-subtle);">Loading Participation Criteria from ClinicalTrials.gov...</span>`;
  }

  try {
    const response = await fetch(`/api/trials/${encodeURIComponent(nctId)}?force_refresh=true`);
    if (!response.ok) {
      throw new Error("Failed to load protocol");
    }
    const study = await response.json();
    trial.participation_criteria = study.criteria || study.participation_criteria || {};
    if (body) {
      body.innerHTML = renderParticipationCriteria(trial);
    }
  } catch (error) {
    if (body) {
      body.innerHTML = `<span style="color: var(--text-subtle);">Could not load Participation Criteria. ${escapeHtml(error.message || "")}</span>`;
    }
  }
}

function toggleDrawer(id) {
  toggleDetails(id);
}

function copyNCT(nctId, btn) {
  navigator.clipboard.writeText(nctId).then(() => {
    const original = btn.textContent;
    btn.textContent = "Copied";
    btn.style.color = "var(--primary)";
    setTimeout(() => {
      btn.textContent = original;
      btn.style.color = "";
    }, 1500);
  });
}

// ==========================================
// REGISTRY MONITOR DASHBOARD LOGIC
// ==========================================

async function loadRegistryMetrics(forceRefresh = false) {
  try {
    const res = await fetch(`/api/registry/metrics${forceRefresh ? "?force_refresh=true" : ""}`);
    if (!res.ok) return;

    const data = await res.json();
    cachedRegistryMetrics = data;

    // Update Hero Cards
    document.getElementById("mon-total-recruiting").textContent = (data.total_recruiting || 0).toLocaleString();
    document.getElementById("mon-new-24h").textContent = `+${data.newly_added?.last_24h ?? 0}`;
    document.getElementById("mon-new-7d-sub").textContent = `${data.newly_added?.last_7d ?? 0} in past 7 days (~${data.newly_added?.daily_average_7d ?? 0}/day)`;

    document.getElementById("mon-upd-24h").textContent = (data.updated_studies?.last_24h ?? 0).toLocaleString();
    document.getElementById("mon-upd-7d-sub").textContent = `${(data.updated_studies?.last_7d ?? 0).toLocaleString()} in past 7 days (~${data.updated_studies?.daily_average_7d ?? 0}/day)`;

    document.getElementById("mon-count-new-tab").textContent = data.newly_added?.last_7d ?? 0;
    document.getElementById("mon-count-upd-tab").textContent = data.updated_studies?.last_7d ?? 0;

    const syncEl = document.getElementById("mon-last-sync-time");
    if (syncEl && data.last_synced_at) {
      const syncDate = new Date(data.last_synced_at);
      syncEl.textContent = syncDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  } catch (e) {
    console.error("Could not load registry metrics:", e);
  }
}

function setMonitorFeedType(type, el) {
  currentMonitorSubtab = type;
  document.querySelectorAll(".monitor-subtab").forEach(tab => tab.classList.remove("active"));
  if (el) el.classList.add("active");
  loadRegistryFeed();
}

async function loadRegistryFeed() {
  const loading = document.getElementById("mon-table-loading");
  const thead = document.getElementById("mon-table-head");
  const tbody = document.getElementById("mon-table-body");
  const days = document.getElementById("mon-days-select").value || 7;

  loading.style.display = "block";
  tbody.innerHTML = "";

  if (currentMonitorSubtab === "history") {
    // Render Historical Snapshots table
    thead.innerHTML = `
      <tr>
        <th>Date</th>
        <th>Total Active Recruiting</th>
        <th>Newly Added (24h)</th>
        <th>Updated (24h)</th>
        <th>Weekly Newly Added</th>
        <th>Recorded At</th>
      </tr>
    `;

    try {
      const res = await fetch(`/api/registry/history?limit_days=${days}`);
      const history = await res.json();
      loading.style.display = "none";

      if (!history || history.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-subtle);">No historical snapshots recorded yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = history.map(h => `
        <tr>
          <td class="td-date">${h.snapshot_date}</td>
          <td style="font-weight: 700; color: var(--primary);">${(h.total_recruiting || 0).toLocaleString()}</td>
          <td style="color: var(--success); font-weight: 600;">+${h.new_24h}</td>
          <td style="color: var(--warning); font-weight: 600;">${h.updated_24h}</td>
          <td>+${h.new_7d}</td>
          <td class="td-date" style="font-size: 0.725rem;">${new Date(h.recorded_at).toLocaleString()}</td>
        </tr>
      `).join("");
    } catch (e) {
      loading.style.display = "none";
      tbody.innerHTML = `<tr><td colspan="6" style="color: var(--danger);">Failed to load historical snapshots.</td></tr>`;
    }
    return;
  }

  // Render Newly Added or Recently Updated Study Feed
  const dateColTitle = currentMonitorSubtab === "new" ? "First Posted" : "Last Updated";
  thead.innerHTML = `
    <tr>
      <th>NCT ID</th>
      <th>Study Title</th>
      <th>Status</th>
      <th>${dateColTitle}</th>
      <th>Conditions</th>
      <th>Lead Sponsor</th>
    </tr>
  `;

  try {
    const res = await fetch(`/api/registry/feed?type=${currentMonitorSubtab}&days=${days}&limit=30`);
    const studies = await res.json();
    loading.style.display = "none";

    if (!studies || studies.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-subtle);">No studies recorded in this window.</td></tr>`;
      return;
    }

    tbody.innerHTML = studies.map(s => {
      const dateVal = currentMonitorSubtab === "new" ? (s.first_posted || "—") : (s.last_updated || "—");
      return `
        <tr>
          <td>
            <div style="display: flex; align-items: center; gap: 0.35rem;">
              <a href="${s.web_url}" target="_blank" rel="noopener noreferrer" class="nct-link">
                ${s.nct_id} ↗
              </a>
              <button type="button" class="btn-copy-chip" onclick="copyNCT('${s.nct_id}', this)">Copy</button>
            </div>
          </td>
          <td class="td-study-title">${escapeHtml(s.title)}</td>
          <td><span class="status-chip">${s.status}</span></td>
          <td class="td-date">${dateVal}</td>
          <td style="color: var(--text-muted); font-size: 0.775rem;">${(s.conditions || []).join(", ") || "—"}</td>
          <td style="color: var(--text-subtle); font-size: 0.775rem;">${escapeHtml(s.lead_sponsor || "—")}</td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    loading.style.display = "none";
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--danger);">Failed to load registry feed.</td></tr>`;
  }
}

function formatHealthyVolunteers(demo) {
  const value = demo?.healthy_volunteers;
  if (value === true || value === "Yes" || value === "YES" || value === "true") {
    return "Accepts Healthy Volunteers";
  }
  if (value === false || value === "No" || value === "NO" || value === "false") {
    return "Does not accept healthy volunteers";
  }
  return "Not specified";
}

function formatAgeBound(years, text) {
  if (text) return text;
  if (years != null && years !== "") return `${years} Years`;
  return "None";
}

function renderParticipationCriteria(trial) {
  const evaluations = trial.criteria_evaluations || [];
  if (evaluations.length) {
    return `
      <div class="criteria-rows-box">
        ${evaluations.map((criterion) => {
          let cellClass = "info";
          if (criterion.label === "included" || criterion.label === "not excluded") cellClass = "included";
          else if (criterion.label === "excluded" || criterion.label === "not included") cellClass = "excluded";
          return `
            <div class="criteria-cell">
              <div class="cell-top">
                <span class="cell-type">${escapeHtml((criterion.criterion_type || "CRITERION").toUpperCase())} #${criterion.criterion_index + 1}</span>
                <span class="cell-verdict ${cellClass}">${escapeHtml(criterion.label)}</span>
              </div>
              <div class="cell-text">${escapeHtml(criterion.criterion_text)}</div>
              <div class="cell-reason"><strong>Match Assessment:</strong> ${escapeHtml(criterion.reasoning)}</div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  const protocol = trial.participation_criteria || {};
  const inclusions = protocol.inclusion_criteria || [];
  const exclusions = protocol.exclusion_criteria || [];
  const rawText = (protocol.raw_text || "").trim();

  const renderList = (items, title) => {
    if (!items.length) return "";
    return `
      <div class="criteria-protocol-block">
        <div class="criteria-protocol-title">${title}</div>
        <ol class="criteria-protocol-list">
          ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ol>
      </div>
    `;
  };

  if (inclusions.length || exclusions.length) {
    return `${renderList(inclusions, "Inclusion Criteria")}${renderList(exclusions, "Exclusion Criteria")}`;
  }
  if (rawText) {
    return `<pre class="criteria-raw-text">${escapeHtml(rawText)}</pre>`;
  }
  return `<span style="color: var(--text-subtle);">No Participation Criteria were published for this study.</span>`;
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text) {
  if (!text) return "";
  return String(text).replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

// ==========================================
// INTERACTIVE ELIGIBILITY SCREENER MODAL
// ==========================================

async function openEligibilityQuestionnaire(nctId, trialTitle) {
  const modal = document.getElementById("eligibility-modal");
  const titleEl = document.getElementById("quest-trial-title");
  const nctEl = document.getElementById("quest-nct-id");
  const loadingEl = document.getElementById("quest-loading");
  const qContainer = document.getElementById("quest-questions-container");
  const vContainer = document.getElementById("quest-verdict-container");

  if (!modal) return;

  currentActiveQuestNctId = nctId;
  currentQuestData = null;
  userQuestAnswers = {};

  if (titleEl) titleEl.textContent = trialTitle || "Check Your Eligibility";
  if (nctEl) nctEl.textContent = `NCT ID: ${nctId}`;

  const modalBadgeEl = document.getElementById("quest-modal-badge");
  if (modalBadgeEl) modalBadgeEl.textContent = "⚡ Real-Time AI Screener (Groq LPU)";

  if (loadingEl) {
    loadingEl.style.display = "flex";
    loadingEl.innerHTML = `
      <div class="spinner-clean"></div>
      <p style="margin-top: 0.75rem; font-weight: 600; color: var(--text-main);">Translating protocol into plain-language questions...</p>
      <span style="font-size: 0.78rem; color: var(--text-subtle); margin-top: 0.25rem;">⚡ Real-time patient rephrasing powered by Groq LPU (~250ms)</span>
    `;
  }
  if (qContainer) qContainer.style.display = "none";
  if (vContainer) vContainer.style.display = "none";

  modal.style.display = "flex";
  document.body.style.overflow = "hidden"; // Prevent page background scrolling

  try {
    const res = await fetch(`/api/trials/${encodeURIComponent(nctId)}/questionnaire`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || err.detail || `HTTP ${res.status}: Failed to generate questionnaire`);
    }
    const data = await res.json();
    currentQuestData = data;
    renderQuestionnaire(data);
  } catch (err) {
    if (loadingEl) {
      loadingEl.innerHTML = `
        <div style="padding: 2rem 1rem; text-align: center;">
          <div style="font-size: 2rem; margin-bottom: 0.5rem;">⚠️</div>
          <h4 style="font-weight: 700; color: var(--danger); margin-bottom: 0.5rem;">Could not load screener</h4>
          <p style="font-size: 0.85rem; color: var(--text-muted); max-width: 440px; margin: 0 auto;">${escapeHtml(err.message)}</p>
          <button type="button" class="btn-modal-cancel" style="margin-top: 1.25rem;" onclick="closeEligibilityModal()">Close Window</button>
        </div>
      `;
    }
  }
}

function renderQuestionnaire(data) {
  const loadingEl = document.getElementById("quest-loading");
  const qContainer = document.getElementById("quest-questions-container");
  const bannerEl = document.getElementById("quest-pre-answered");
  const stepViewEl = document.getElementById("wizard-step-view");

  if (loadingEl) loadingEl.style.display = "none";
  if (qContainer) qContainer.style.display = "block";

  const preDemo = data.pre_answered_demographics || {};
  const targetLabel = currentSearchTarget === "myself" ? "your profile (Age: 52, Female)" : "entered demographics";
  const engine = data.engine || "GROQ";
  let engineBadge = `<span class="wizard-engine-badge groq">⚡ Groq LPU AI</span>`;
  const modalBadgeEl = document.getElementById("quest-modal-badge");
  if (engine === "CACHE_HIT") {
    engineBadge = `<span class="wizard-engine-badge cache">⚡ Cached</span>`;
    if (modalBadgeEl) modalBadgeEl.textContent = "⚡ Real-Time AI Screener (Cached)";
  } else if (engine === "GROQ") {
    if (modalBadgeEl) modalBadgeEl.textContent = "⚡ Real-Time AI Screener (Groq LPU)";
  } else if (engine === "OPENAI") {
    engineBadge = `<span class="wizard-engine-badge openai">⚡ OpenAI AI</span>`;
    if (modalBadgeEl) modalBadgeEl.textContent = "⚡ Real-Time AI Screener (OpenAI)";
  } else if (engine === "OFFLINE" || engine === "OFFLINE_RULE_FALLBACK") {
    engineBadge = `<span class="wizard-engine-badge" style="background: var(--bg-subtle); color: var(--text-muted);">✓ Rule Engine</span>`;
    if (modalBadgeEl) modalBadgeEl.textContent = "✓ Local Rule Screener";
  }

  if (bannerEl) {
    const qList = data.questions || [];
    const incTotal = qList.filter(q => (q.category || "").toUpperCase() === "INCLUSION").length;
    const excTotal = qList.filter(q => (q.category || "").toUpperCase() === "EXCLUSION").length;
    const breakdownPill = qList.length > 0 ? `
      <div style="font-size: 0.73rem; background: rgba(14, 165, 233, 0.1); color: #0284c7; font-weight: 700; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(14, 165, 233, 0.25);">
        🎯 ${incTotal} Inclusions • 🛡️ ${excTotal} Exclusions
      </div>
    ` : "";

    bannerEl.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;">
        <div>
          <strong>✓ Demographics Pre-Screened:</strong> Age (${escapeHtml(preDemo.minimum_age || "All")} to ${escapeHtml(preDemo.maximum_age || "All")}) & Sex (${escapeHtml(preDemo.sex_restriction || "Both")}) verified from ${targetLabel}.
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
          ${breakdownPill}
          ${engineBadge}
          <div style="font-size: 0.73rem; background: rgba(16, 185, 129, 0.15); color: #059669; font-weight: 700; padding: 2px 8px; border-radius: 4px;">
            ✓ Automated
          </div>
        </div>
      </div>
    `;
  }

  // Handle empty question list (all determined by demographics)
  if (!data.questions || data.questions.length === 0) {
    const trackerEl = document.querySelector(".wizard-header-tracker");
    if (trackerEl) trackerEl.style.display = "none";
    if (stepViewEl) {
      stepViewEl.innerHTML = `
        <div class="wizard-card" style="text-align: center; padding: 2.5rem 1.5rem;">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📋</div>
          <h4 style="font-weight: 700; color: var(--text-main); margin-bottom: 0.35rem;">No Additional Questions Needed</h4>
          <p style="font-size: 0.85rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 1.25rem;">
            This clinical study's requirements are fully determined by your demographic clearance.
          </p>
          <button type="button" class="btn-modal-submit" onclick="submitEligibilityAnswers()">
            Finalize Screener &amp; See Verdict ➔
          </button>
        </div>
      `;
    }
    const footerEl = document.querySelector(".wizard-footer");
    if (footerEl) footerEl.style.display = "none";
    return;
  }

  const trackerEl = document.querySelector(".wizard-header-tracker");
  if (trackerEl) trackerEl.style.display = "block";
  const footerEl = document.querySelector(".wizard-footer");
  if (footerEl) footerEl.style.display = "flex";

  wizardCurrentStep = 0;

  // Bind keyboard navigation
  window.removeEventListener("keydown", handleWizardKeydown);
  window.addEventListener("keydown", handleWizardKeydown);

  renderWizardStep();
}

function renderWizardStep() {
  const questions = currentQuestData?.questions || [];
  const total = questions.length;
  if (total === 0) return;

  if (wizardCurrentStep < 0) wizardCurrentStep = 0;
  if (wizardCurrentStep >= total) wizardCurrentStep = total - 1;

  const q = questions[wizardCurrentStep];
  const stepNum = wizardCurrentStep + 1;
  const progressPct = Math.round((stepNum / total) * 100);

  // 1. Update Tracker Meta & Progress Bar
  const counterEl = document.getElementById("wizard-step-counter");
  const pctEl = document.getElementById("wizard-progress-pct");
  const fillEl = document.getElementById("wizard-progress-fill");
  const pillsEl = document.getElementById("wizard-step-pills");

  if (counterEl) counterEl.textContent = `Question ${stepNum} of ${total}`;
  if (pctEl) pctEl.textContent = `${progressPct}% Completed`;
  if (fillEl) fillEl.style.width = `${progressPct}%`;

  // 2. Render Step Pills / Dots
  if (pillsEl) {
    pillsEl.innerHTML = questions.map((item, idx) => {
      const isCurrent = idx === wizardCurrentStep;
      const ans = userQuestAnswers[item.id];
      let pillClass = "wizard-pill-dot";
      let pillContent = idx + 1;
      let title = `Question ${idx + 1}`;

      if (isCurrent) {
        pillClass += " active";
        title += " (Current)";
      } else if (ans) {
        pillClass += " completed";
        pillContent = "✓";
        title += ` (Answered: ${ans})`;
      }

      return `
        <button type="button" class="${pillClass}" onclick="goToWizardStep(${idx})" title="${escapeAttr(title)}" aria-label="${escapeAttr(title)}">
          ${pillContent}
        </button>
      `;
    }).join("");
  }

  // 3. Render Active Question Tile
  const viewEl = document.getElementById("wizard-step-view");
  if (viewEl) {
    const isExclusion = (q.category || "").toUpperCase() === "EXCLUSION";
    const categoryClass = isExclusion ? "exclusion" : "inclusion";
    const categoryLabel = isExclusion ? "🛡️ Safety Exclusion Rule • Must Not Have" : "🎯 Disease Requirement • Inclusion";
    const userAns = userQuestAnswers[q.id];

    viewEl.innerHTML = `
      <div class="wizard-card">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <span class="wizard-category-badge ${categoryClass}">
            ${categoryLabel}
          </span>
          <span style="font-size: 0.72rem; font-weight: 600; color: var(--text-subtle); background: var(--bg-subtle); padding: 2px 7px; border-radius: 4px;">
            Target: <strong>${escapeHtml(q.favorable_answer || (isExclusion ? "NO" : "YES"))}</strong>
          </span>
        </div>

        <div class="wizard-qtitle">${escapeHtml(q.question_text)}</div>

        ${q.why_it_matters ? `
          <div class="wizard-why-box">
            <span class="wizard-why-icon">💡</span>
            <span class="wizard-why-text"><strong>Why doctors check this:</strong> ${escapeHtml(q.why_it_matters)}</span>
          </div>
        ` : ""}

        ${q.original_criterion ? `
          <details class="wizard-protocol-details">
            <summary class="wizard-protocol-summary">
              🔍 View original medical protocol excerpt
            </summary>
            <div class="wizard-protocol-text">
              "${escapeHtml(q.original_criterion)}"
            </div>
          </details>
        ` : ""}

        <div class="wizard-options-grid">
          <!-- Option YES -->
          <div class="wizard-option-tile ${userAns === "YES" ? "selected-yes" : ""}" id="wopt-${q.id}-YES" onclick="selectQuestAnswer('${q.id}', 'YES')">
            <div class="wizard-option-left">
              <span class="wizard-opt-icon">👍</span>
              <div class="wizard-opt-text-col">
                <span class="wizard-opt-heading">Yes</span>
                <span class="wizard-opt-subtext">I have this condition / This applies to me</span>
              </div>
            </div>
            <span class="wizard-opt-key">1</span>
          </div>

          <!-- Option NO -->
          <div class="wizard-option-tile ${userAns === "NO" ? "selected-no" : ""}" id="wopt-${q.id}-NO" onclick="selectQuestAnswer('${q.id}', 'NO')">
            <div class="wizard-option-left">
              <span class="wizard-opt-icon">👎</span>
              <div class="wizard-opt-text-col">
                <span class="wizard-opt-heading">No</span>
                <span class="wizard-opt-subtext">I do not have this / Does not apply to me</span>
              </div>
            </div>
            <span class="wizard-opt-key">2</span>
          </div>

          <!-- Option NOT_SURE -->
          <div class="wizard-option-tile ${userAns === "NOT_SURE" ? "selected-unsure" : ""}" id="wopt-${q.id}-NOT_SURE" onclick="selectQuestAnswer('${q.id}', 'NOT_SURE')">
            <div class="wizard-option-left">
              <span class="wizard-opt-icon">❓</span>
              <div class="wizard-opt-text-col">
                <span class="wizard-opt-heading">Not Sure / Ask Doctor</span>
                <span class="wizard-opt-subtext">I am unsure; my doctor will verify from clinical records</span>
              </div>
            </div>
            <span class="wizard-opt-key">3</span>
          </div>
        </div>
      </div>
    `;
  }

  // 4. Update Footer Controls
  const prevBtn = document.getElementById("btn-wizard-prev");
  const nextBtn = document.getElementById("btn-wizard-next");
  const submitBtn = document.getElementById("btn-wizard-submit");

  if (prevBtn) {
    prevBtn.disabled = wizardCurrentStep === 0;
  }

  const isLast = wizardCurrentStep === total - 1;
  if (isLast) {
    if (nextBtn) nextBtn.style.display = "none";
    if (submitBtn) {
      submitBtn.style.display = "inline-flex";
    }
  } else {
    if (nextBtn) nextBtn.style.display = "inline-flex";
    if (submitBtn) submitBtn.style.display = "none";
  }
}

function selectQuestAnswer(qId, choice) {
  if (wizardAutoAdvanceTimer) {
    clearTimeout(wizardAutoAdvanceTimer);
    wizardAutoAdvanceTimer = null;
  }

  userQuestAnswers[qId] = choice;

  // Immediate UI styling update on the current card
  const choices = ["YES", "NO", "NOT_SURE"];
  choices.forEach(c => {
    const tile = document.getElementById(`wopt-${qId}-${c}`);
    if (tile) {
      tile.classList.remove("selected-yes", "selected-no", "selected-unsure");
      if (c === choice) {
        if (choice === "YES") tile.classList.add("selected-yes");
        else if (choice === "NO") tile.classList.add("selected-no");
        else tile.classList.add("selected-unsure");
      }
    }
  });

  // Update pills immediately
  const pillsEl = document.getElementById("wizard-step-pills");
  const questions = currentQuestData?.questions || [];
  if (pillsEl && questions.length) {
    const currentPill = pillsEl.children[wizardCurrentStep];
    if (currentPill) {
      currentPill.classList.add("completed");
      currentPill.textContent = "✓";
    }
  }

  const total = questions.length;
  // If not on last step, auto-advance after 320ms
  if (wizardCurrentStep < total - 1) {
    wizardAutoAdvanceTimer = setTimeout(() => {
      goToNextWizardStep();
    }, 320);
  } else {
    // If last step, ensure submit button is visible & focused
    const submitBtn = document.getElementById("btn-wizard-submit");
    if (submitBtn) {
      submitBtn.style.display = "inline-flex";
      submitBtn.focus();
    }
  }
}

function goToNextWizardStep() {
  if (wizardAutoAdvanceTimer) {
    clearTimeout(wizardAutoAdvanceTimer);
    wizardAutoAdvanceTimer = null;
  }

  const questions = currentQuestData?.questions || [];
  if (!questions.length) return;

  // If user advances without answering, default to NOT_SURE so they are never blocked
  const curQ = questions[wizardCurrentStep];
  if (curQ && !userQuestAnswers[curQ.id]) {
    userQuestAnswers[curQ.id] = "NOT_SURE";
  }

  if (wizardCurrentStep < questions.length - 1) {
    wizardCurrentStep++;
    renderWizardStep();
  }
}

function goToPrevWizardStep() {
  if (wizardAutoAdvanceTimer) {
    clearTimeout(wizardAutoAdvanceTimer);
    wizardAutoAdvanceTimer = null;
  }

  if (wizardCurrentStep > 0) {
    wizardCurrentStep--;
    renderWizardStep();
  }
}

function goToWizardStep(stepIdx) {
  if (wizardAutoAdvanceTimer) {
    clearTimeout(wizardAutoAdvanceTimer);
    wizardAutoAdvanceTimer = null;
  }

  const questions = currentQuestData?.questions || [];
  if (stepIdx >= 0 && stepIdx < questions.length) {
    wizardCurrentStep = stepIdx;
    renderWizardStep();
  }
}

function handleWizardKeydown(e) {
  const modal = document.getElementById("eligibility-modal");
  if (!modal || modal.style.display === "none") return;
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

  const questions = currentQuestData?.questions || [];
  if (!questions.length) return;
  const curQ = questions[wizardCurrentStep];
  if (!curQ) return;

  if (e.key === "1" || e.key.toLowerCase() === "y") {
    e.preventDefault();
    selectQuestAnswer(curQ.id, "YES");
  } else if (e.key === "2" || e.key.toLowerCase() === "n") {
    e.preventDefault();
    selectQuestAnswer(curQ.id, "NO");
  } else if (e.key === "3" || e.key.toLowerCase() === "u") {
    e.preventDefault();
    selectQuestAnswer(curQ.id, "NOT_SURE");
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    goToPrevWizardStep();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    goToNextWizardStep();
  } else if (e.key === "Enter") {
    if (wizardCurrentStep === questions.length - 1) {
      e.preventDefault();
      submitEligibilityAnswers();
    } else {
      e.preventDefault();
      goToNextWizardStep();
    }
  }
}

async function submitEligibilityAnswers(e) {
  if (e) e.preventDefault();

  if (wizardAutoAdvanceTimer) {
    clearTimeout(wizardAutoAdvanceTimer);
    wizardAutoAdvanceTimer = null;
  }
  window.removeEventListener("keydown", handleWizardKeydown);

  const submitBtn = document.getElementById("btn-wizard-submit") || document.getElementById("btn-submit-quest");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>Evaluating Criteria against Protocol...</span>`;
  }

  // Build answers list
  const answersList = [];
  if (currentQuestData?.questions) {
    for (const q of currentQuestData.questions) {
      answersList.push({
        question_id: q.id,
        answer: userQuestAnswers[q.id] || "NOT_SURE",
      });
    }
  }

  const payload = {
    nct_id: currentActiveQuestNctId,
    answers: answersList,
  };

  try {
    const res = await fetch(`/api/trials/${encodeURIComponent(currentActiveQuestNctId)}/evaluate-eligibility`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || err.detail || "Eligibility evaluation failed");
    }

    const evalResult = await res.json();
    renderVerdictResult(evalResult);
  } catch (err) {
    alert(`Evaluation Error: ${err.message}`);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span>Submit Answers & See Verdict ➔</span>`;
    }
  }
}

let currentVerdictData = null;
let currentVerdictFilter = "ALL";

function renderVerdictResult(result) {
  const qContainer = document.getElementById("quest-questions-container");
  const vContainer = document.getElementById("quest-verdict-container");
  const modalBadgeEl = document.getElementById("quest-modal-badge");

  if (qContainer) qContainer.style.display = "none";
  if (vContainer) vContainer.style.display = "block";
  if (modalBadgeEl) modalBadgeEl.textContent = "⚡ Protocol Eligibility Verdict";

  currentVerdictData = result;
  currentVerdictFilter = "ALL";

  // Update the trial entry in currentTrials so dashboard immediately updates card verdict, badge, and score
  if (currentActiveQuestNctId && Array.isArray(currentTrials)) {
    const target = currentTrials.find(t => t.nct_id === currentActiveQuestNctId);
    if (target) {
      target.verdict = result.verdict;
      target.eligibility_score = result.score;
      target.summary_reasoning = `Self-Screened (${Math.round((result.score || 0) * 100)}%): ${result.summary}`;
      target._is_self_screened = true;
      updateFilterPills();
      renderCards();
    }
  }

  let cardClass = "likely";
  let verdictTitle = "Likely Eligible • Clinical Review Needed";
  let verdictBadgeLabel = "Likely Eligible";
  let verdictBadgeClass = "likely";
  let verdictIcon = "✓";

  if (result.verdict === "ELIGIBLE") {
    cardClass = "eligible";
    verdictTitle = "Eligible • Strong Protocol Match";
    verdictBadgeLabel = "Eligible Match";
    verdictBadgeClass = "eligible";
    verdictIcon = "🎉";
  } else if (result.verdict === "INELIGIBLE") {
    cardClass = "ineligible";
    verdictTitle = "Protocol Requirements Not Met";
    verdictBadgeLabel = "Ineligible";
    verdictBadgeClass = "ineligible";
    verdictIcon = "✕";
  } else if (result.verdict === "UNCERTAIN") {
    cardClass = "uncertain";
    verdictTitle = "Eligibility Uncertain • Clinical Records Needed";
    verdictBadgeLabel = "Status Uncertain";
    verdictBadgeClass = "uncertain";
    verdictIcon = "❓";
  }

  const scorePercent = Math.round((result.score || 0) * 100);
  const evals = result.criteria_evaluations || [];
  const incEvals = evals.filter(e => (e.category || "").toUpperCase() === "INCLUSION");
  const excEvals = evals.filter(e => (e.category || "").toUpperCase() === "EXCLUSION");

  const incMet = incEvals.filter(e => e.status === "MET").length;
  const incUnmet = incEvals.filter(e => e.status === "UNMET").length;
  const incUnsure = incEvals.filter(e => e.status === "UNCERTAIN").length;

  const excMet = excEvals.filter(e => e.status === "MET").length;
  const excUnmet = excEvals.filter(e => e.status === "UNMET").length;
  const excUnsure = excEvals.filter(e => e.status === "UNCERTAIN").length;

  const metCount = evals.filter(e => e.status === "MET").length;
  const unmetCount = evals.filter(e => e.status === "UNMET").length;
  const unsureCount = evals.filter(e => e.status === "UNCERTAIN").length;

  const criteriaMatchPercent = result.criteria_match_percentage !== undefined
    ? result.criteria_match_percentage
    : (evals.length > 0 ? Math.round((metCount / evals.length) * 100) : 0);

  let scoreLabel = `Protocol Confidence: <strong>${scorePercent}%</strong>`;
  if (result.verdict === "INELIGIBLE") {
    scoreLabel = `Protocol Clearance: <strong>${scorePercent}% • Disqualified</strong>`;
  } else if (result.verdict === "UNCERTAIN") {
    scoreLabel = `Protocol Clearance: <strong>${scorePercent}% • Needs Medical Data</strong>`;
  }

  if (vContainer) {
    vContainer.innerHTML = `
      <div class="verdict-hero-card ${cardClass}">
        <span class="verdict-pill-badge ${verdictBadgeClass}">
          <span>${verdictIcon}</span> ${verdictBadgeLabel}
        </span>
        <div style="font-size: 1.15rem; font-weight: 800; color: var(--text-main);">
          ${verdictTitle}
        </div>
        <div class="verdict-score-row" style="flex-wrap: wrap; gap: 0.5rem; align-items: center;">
          <span class="verdict-score-badge">
            ${scoreLabel}
          </span>
          <span class="verdict-score-badge" style="background: rgba(14, 165, 233, 0.12); color: #0284c7; border: 1px solid rgba(14, 165, 233, 0.25);">
            Criteria Match: <strong>${criteriaMatchPercent}%</strong> (${metCount}/${evals.length} Met)
          </span>
          <span style="font-size: 0.725rem; color: var(--text-subtle);">
            ⚡ Verified against Study Protocol
          </span>
        </div>

        ${result.cohort_qualified ? `
          <div style="margin: 0.5rem 0 0.25rem 0; padding: 0.5rem 0.85rem; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; font-size: 0.8rem; color: #065f46; display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 1.1rem;">🎯</span>
            <div>
              <strong>Qualified Study Arm:</strong> ${escapeHtml(result.cohort_qualified)}
              <span style="display: block; font-size: 0.72rem; color: #047857; margin-top: 1px;">
                💡 Answering 'No' to alternative cohorts did not penalize your match because you satisfied this study arm.
              </span>
            </div>
          </div>
        ` : ''}
        
        <!-- Criteria Distribution Breakdown (Disease Fit vs Safety Clearance) -->
        <div class="verdict-stats-row">
          ${incEvals.length > 0 ? `
            <span class="verdict-stat-chip ${incUnmet > 0 ? 'unmet' : (incMet === incEvals.length ? 'met' : 'likely')}">
              🎯 Disease Requirements: ${incMet}/${incEvals.length} Met ${incUnmet > 0 ? `(${incUnmet} Failed)` : ''}
            </span>
          ` : ''}
          ${excEvals.length > 0 ? `
            <span class="verdict-stat-chip ${excUnmet > 0 ? 'unmet' : (excMet === excEvals.length ? 'met' : 'likely')}">
              🛡️ Safety Rules: ${excMet}/${excEvals.length} Cleared ${excUnmet > 0 ? `(${excUnmet} Triggered)` : ''}
            </span>
          ` : ''}
        </div>

        <div class="verdict-stats-row" style="margin-top: 0.35rem;">
          <span class="verdict-stat-chip met">✓ ${metCount} Total Met</span>
          ${unmetCount > 0 ? `<span class="verdict-stat-chip unmet">✕ ${unmetCount} Total Unmet</span>` : ""}
          ${unsureCount > 0 ? `<span class="verdict-stat-chip unsure">? ${unsureCount} Unsure</span>` : ""}
        </div>

        <p class="verdict-summary-p">
          ${escapeHtml(result.summary)}
        </p>
      </div>

      <!-- Criteria Filter & Breakdown -->
      <div class="verdict-filter-toolbar">
        <h5 style="font-size: 0.8rem; font-weight: 700; color: var(--text-main); margin: 0;">
          Evaluated Criteria (${evals.length})
        </h5>
        <div class="verdict-filter-tabs">
          <button type="button" class="verdict-tab-btn active" id="vtab-ALL" onclick="setVerdictFilter('ALL')">All (${evals.length})</button>
          ${incEvals.length > 0 ? `<button type="button" class="verdict-tab-btn" id="vtab-INCLUSION" onclick="setVerdictFilter('INCLUSION')">🎯 Inclusions (${incEvals.length})</button>` : ''}
          ${excEvals.length > 0 ? `<button type="button" class="verdict-tab-btn" id="vtab-EXCLUSION" onclick="setVerdictFilter('EXCLUSION')">🛡️ Exclusions (${excEvals.length})</button>` : ''}
          <button type="button" class="verdict-tab-btn" id="vtab-MET" onclick="setVerdictFilter('MET')">Met (${metCount})</button>
          ${unmetCount > 0 ? `<button type="button" class="verdict-tab-btn" id="vtab-UNMET" onclick="setVerdictFilter('UNMET')">Unmet (${unmetCount})</button>` : ''}
          ${unsureCount > 0 ? `<button type="button" class="verdict-tab-btn" id="vtab-UNCERTAIN" onclick="setVerdictFilter('UNCERTAIN')">Unsure (${unsureCount})</button>` : ''}
        </div>
      </div>

      <div class="verdict-crit-list" id="verdict-crit-list-container">
        ${renderVerdictCritList(evals, "ALL")}
      </div>

      <!-- Condition-Aware Doctor Checklist -->
      ${result.doctor_checklist && result.doctor_checklist.length ? `
        <div class="verdict-doc-card">
          <div class="verdict-doc-head">
            <div class="verdict-doc-title">
              <span>🩺</span> Doctor Consultation Checklist
            </div>
            <button type="button" class="btn-copy-doc" onclick="copyDoctorChecklist()" title="Copy checklist to clipboard">
              📋 Copy Checklist
            </button>
          </div>
          <ul class="verdict-doc-list">
            ${result.doctor_checklist.map(ch => `<li>${escapeHtml(ch)}</li>`).join("")}
          </ul>
        </div>
      ` : ""}

      <!-- Verdict Actions -->
      <div class="modal-footer" style="margin-top: 1.15rem;">
        <button type="button" class="btn-modal-cancel" onclick="retakeScreener()">
          <span>↺ Retake Questions</span>
        </button>
        <button type="button" class="btn-modal-cancel" onclick="copyFullVerdictReport()">
          <span>📋 Copy Report</span>
        </button>
        <button type="button" class="btn-modal-submit" onclick="closeEligibilityModal()">
          <span>Done / Close</span>
        </button>
      </div>
    `;
  }
}

function renderVerdictCritList(evals, filter) {
  let filtered = evals;
  if (filter === "INCLUSION" || filter === "EXCLUSION") {
    filtered = evals.filter(e => (e.category || "").toUpperCase() === filter);
  } else if (filter !== "ALL") {
    filtered = evals.filter(e => e.status === filter);
  }

  if (filtered.length === 0) {
    return `<div style="text-align: center; padding: 1.5rem; color: var(--text-muted); font-size: 0.8rem;">No criteria match this filter.</div>`;
  }

  return filtered.map((item, idx) => {
    const isMet = item.status === "MET";
    const isUnmet = item.status === "UNMET";
    const statusClass = isMet ? "met" : (isUnmet ? "unmet" : "uncertain");
    const statusIcon = isMet ? "✓" : (isUnmet ? "✕" : "?");
    const statusLabel = isMet ? "Met" : (isUnmet ? "Unmet" : "Requires Review");
    const isInc = (item.category || "CRITERION").toUpperCase() === "INCLUSION";
    const catLabel = isInc ? "🎯 Disease Requirement (Inclusion)" : "🛡️ Safety Exclusion Rule";

    return `
      <div class="verdict-crit-card ${statusClass}">
        <div class="verdict-crit-icon">${statusIcon}</div>
        <div class="verdict-crit-content">
          <div class="verdict-crit-header">
            <span class="verdict-crit-cat">
              ${catLabel} • Your Answer: <strong>${escapeHtml(item.user_answer)}</strong>
            </span>
            <span class="verdict-crit-badge ${statusClass}">
              ${statusLabel}
            </span>
          </div>
          <div class="verdict-crit-question">
            ${escapeHtml(item.criterion)}
          </div>
          <div class="verdict-crit-reason">
            ${escapeHtml(item.reason)}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function setVerdictFilter(filter) {
  currentVerdictFilter = filter;
  const container = document.getElementById("verdict-crit-list-container");
  if (container && currentVerdictData) {
    container.innerHTML = renderVerdictCritList(currentVerdictData.criteria_evaluations || [], filter);
  }

  document.querySelectorAll(".verdict-tab-btn").forEach(btn => {
    btn.classList.remove("active");
  });
  const activeBtn = document.getElementById(`vtab-${filter}`);
  if (activeBtn) activeBtn.classList.add("active");
}

function copyDoctorChecklist() {
  if (!currentVerdictData?.doctor_checklist) return;
  const text = currentVerdictData.doctor_checklist.map(item => `• ${item}`).join("\n");
  navigator.clipboard.writeText(`DOCTOR CONSULTATION CHECKLIST:\n${text}`).then(() => {
    alert("✓ Doctor checklist copied to clipboard!");
  }).catch(() => {});
}

function copyFullVerdictReport() {
  if (!currentVerdictData) return;
  const nct = currentActiveQuestNctId || "";
  const verdict = currentVerdictData.verdict || "";
  const score = Math.round((currentVerdictData.score || 0) * 100);
  const summary = currentVerdictData.summary || "";
  const evals = (currentVerdictData.criteria_evaluations || [])
    .map(e => `[${e.status}] ${e.criterion} -> ${e.user_answer} (${e.reason})`)
    .join("\n");
  const doc = (currentVerdictData.doctor_checklist || []).map(d => `• ${d}`).join("\n");

  const fullReport = `TRIAL ELIGIBILITY REPORT
Trial NCT ID: ${nct}
Verdict: ${verdict} (Confidence: ${score}%)
Summary: ${summary}

CRITERIA EVALUATIONS:
${evals}

DOCTOR CHECKLIST:
${doc}`;

  navigator.clipboard.writeText(fullReport).then(() => {
    alert("✓ Full eligibility report copied to clipboard!");
  }).catch(() => {});
}

function retakeScreener() {
  userQuestAnswers = {};
  wizardCurrentStep = 0;
  if (currentQuestData) {
    renderQuestionnaire(currentQuestData);
  }
}

function closeEligibilityModal() {
  const modal = document.getElementById("eligibility-modal");
  if (modal) modal.style.display = "none";
  document.body.style.overflow = ""; // Restore scrolling

  if (wizardAutoAdvanceTimer) {
    clearTimeout(wizardAutoAdvanceTimer);
    wizardAutoAdvanceTimer = null;
  }
  window.removeEventListener("keydown", handleWizardKeydown);
}

// ============================================================
// PATIENT STUDY SUMMARY MODAL (GROQ LPU TRANSLATION & GLOSSARY)
// ============================================================

let currentActiveSummaryNctId = null;
let currentActiveSummaryTitle = null;

async function openPatientSummaryModal(nctId, trialTitle) {
  currentActiveSummaryNctId = nctId;
  currentActiveSummaryTitle = trialTitle || nctId;

  const modal = document.getElementById("patient-summary-modal");
  const metaEl = document.getElementById("summary-nct-meta");
  const titleEl = document.getElementById("summary-plain-title");
  const loadingEl = document.getElementById("summary-loading");
  const contentEl = document.getElementById("summary-content");

  if (metaEl) metaEl.textContent = `${nctId} • ${trialTitle || "Study Protocol"}`;
  if (titleEl) titleEl.textContent = "Translating Study Protocol...";
  if (loadingEl) loadingEl.style.display = "flex";
  if (contentEl) contentEl.style.display = "none";
  if (modal) modal.style.display = "flex";
  document.body.style.overflow = "hidden";

  try {
    const res = await fetch(`/api/trials/${encodeURIComponent(nctId)}/patient-summary`);
    if (!res.ok) {
      throw new Error(`Summary API returned ${res.status}`);
    }
    const data = await res.json();
    renderPatientSummary(data);
  } catch (err) {
    console.error("Failed to fetch patient summary:", err);
    if (loadingEl) loadingEl.style.display = "none";
    if (contentEl) {
      contentEl.style.display = "block";
      contentEl.innerHTML = `
        <div class="quest-error-card">
          <h4>Unable to generate summary</h4>
          <p>${escapeHtml(err.message || "Failed to contact summary service.")}</p>
          <button type="button" class="btn-clean-refresh" onclick="openPatientSummaryModal('${nctId}', '${escapeAttr(trialTitle)}')">Retry Translation ↻</button>
        </div>
      `;
    }
  }
}

function closePatientSummaryModal() {
  const modal = document.getElementById("patient-summary-modal");
  if (modal) modal.style.display = "none";
  document.body.style.overflow = "";
}

function renderPatientSummary(data) {
  const loadingEl = document.getElementById("summary-loading");
  const contentEl = document.getElementById("summary-content");
  const titleEl = document.getElementById("summary-plain-title");
  const badgeEl = document.getElementById("summary-modal-badge");

  if (titleEl) titleEl.textContent = data.plain_title || "Study Plain-English Summary";
  if (badgeEl) {
    badgeEl.textContent = data.cached ? "⚡ Plain-English Summary (Instant Cache Hit)" : "⚡ Plain-English Summary (Groq LPU ~250ms)";
  }
  if (loadingEl) loadingEl.style.display = "none";
  if (!contentEl) return;

  contentEl.style.display = "block";

  const terms = data.complex_terms_explained || [];

  contentEl.innerHTML = `
    <!-- Hero Box: Plain Title & Overview -->
    <div class="summary-hero-card">
      <div class="summary-hero-title">
        ${escapeHtml(data.plain_title)}
      </div>
      <p style="font-size: 0.875rem; color: var(--text-main); line-height: 1.5; margin: 0;">
        ${escapeHtml(data.what_this_study_is_about)}
      </p>
    </div>

    <!-- 2x2 Grid: Treatment, Participation, Who Can Join -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-card-head">
          <span style="font-size: 1.1rem;">💊</span>
          <span>The Treatment &amp; How It Works</span>
        </div>
        <p class="summary-card-p">
          ${escapeHtml(data.treatment_and_how_it_works)}
        </p>
      </div>

      <div class="summary-card">
        <div class="summary-card-head">
          <span style="font-size: 1.1rem;">🗓️</span>
          <span>What Taking Part Involves</span>
        </div>
        <p class="summary-card-p">
          ${escapeHtml(data.what_participation_involves)}
        </p>
      </div>

      <div class="summary-card" style="grid-column: 1 / -1;">
        <div class="summary-card-head">
          <span style="font-size: 1.1rem;">👥</span>
          <span>Who Doctors Are Looking For</span>
        </div>
        <p class="summary-card-p">
          ${escapeHtml(data.who_can_join_overview)}
        </p>
      </div>
    </div>

    <!-- Plain-English Participation Criteria (Inclusions & Exclusions) -->
    ${((data.plain_inclusions && data.plain_inclusions.length) || (data.plain_exclusions && data.plain_exclusions.length)) ? `
      <div class="summary-criteria-section">
        <h4 style="font-size: 0.95rem; font-weight: 800; color: var(--text-main); margin: 0 0 0.65rem 0; display: flex; align-items: center; gap: 0.5rem;">
          <span>📋</span> Participation Criteria in Everyday Language
        </h4>
        <div class="summary-criteria-grid">
          <!-- Inclusions -->
          <div class="summary-crit-card inclusion">
            <div class="summary-crit-head inclusion">
              <span>🎯</span> Key Requirements to Join (${(data.plain_inclusions || []).length})
            </div>
            <ul class="summary-crit-list">
              ${(data.plain_inclusions || []).map(inc => `
                <li class="summary-crit-item">
                  <span class="summary-crit-bullet inclusion">✓</span>
                  <span>${escapeHtml(inc)}</span>
                </li>
              `).join("")}
            </ul>
          </div>

          <!-- Exclusions -->
          <div class="summary-crit-card exclusion">
            <div class="summary-crit-head exclusion">
              <span>🛡️</span> Rules That Prevent Joining (${(data.plain_exclusions || []).length})
            </div>
            <ul class="summary-crit-list">
              ${(data.plain_exclusions || []).map(exc => `
                <li class="summary-crit-item">
                  <span class="summary-crit-bullet exclusion">✕</span>
                  <span>${escapeHtml(exc)}</span>
                </li>
              `).join("")}
            </ul>
          </div>
        </div>
      </div>
    ` : ""}

    <!-- Mini-Glossary of Medical & Drug Terms -->
    ${terms.length > 0 ? `
      <div class="summary-glossary-section">
        <div class="summary-glossary-title">
          <span>💡</span>
          <span>Medical &amp; Drug Terms Explained in Plain English (${terms.length})</span>
        </div>
        <div class="summary-glossary-list">
          ${terms.map(t => `
            <div class="summary-term-item">
              <span class="summary-term-name">${escapeHtml(t.term)}:</span>
              <span>${escapeHtml(t.plain_english)}</span>
            </div>
          `).join("")}
        </div>
      </div>
    ` : ""}

    <!-- Modal Actions -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1.25rem; padding-top: 0.85rem; border-top: 1px solid var(--border-color); flex-wrap: wrap; gap: 0.75rem;">
      <button type="button" class="btn-wizard-nav" onclick="closePatientSummaryModal()" style="border: 1px solid var(--border-color);">
        Close
      </button>
      <button type="button" class="btn-modal-submit" onclick="startScreenerFromSummary()">
        <span>Check My Eligibility for This Study ➔</span>
      </button>
    </div>
  `;
}

function startScreenerFromSummary() {
  const nctId = currentActiveSummaryNctId;
  const title = currentActiveSummaryTitle;
  closePatientSummaryModal();
  if (nctId) {
    openEligibilityQuestionnaire(nctId, title);
  }
}

