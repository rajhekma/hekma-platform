const $ = (sel) => document.querySelector(sel);
const $all = (sel) => document.querySelectorAll(sel);

// ---------------------------------------------------------------------------
// Navigation: Home → category workspace → tool panel
// ---------------------------------------------------------------------------
const NAV_CONFIG = {
  pii: [
    { panel: "predict", label: "Detect" },
    { panel: "validate", label: "Validate" },
    { panel: "mask", label: "Mask" },
    { panel: "batch", label: "Batch" },
    { panel: "anonymize", label: "Anonymize" },
    { panel: "entities", label: "Labels" },
  ],
  phi: [
    { panel: "predict", label: "Detect" },
    { panel: "validate", label: "Validate" },
    { panel: "mask", label: "Mask" },
    { panel: "batch", label: "Batch" },
    { panel: "anonymize", label: "Anonymize" },
    { panel: "entities", label: "Labels" },
  ],
};

const state = { category: null, panel: null };

function showHome() {
  state.category = null;
  state.panel = null;
  $("#view-home").classList.add("view-active");
  $("#view-home").hidden = false;
  $("#view-workspace").classList.remove("view-active");
  $("#view-workspace").hidden = true;
  delete $("#view-workspace").dataset.category;
}

function openCategory(category) {
  state.category = category;
  state.panel = NAV_CONFIG[category][0].panel;

  $("#view-home").classList.remove("view-active");
  $("#view-home").hidden = true;
  $("#view-workspace").hidden = false;
  $("#view-workspace").classList.add("view-active");
  $("#view-workspace").dataset.category = category;

  const pill = $("#workspace-category-pill");
  pill.textContent = category.toUpperCase();
  pill.className = `category-pill ${category}`;

  $("#workspace-title-text").textContent =
    category === "pii" ? "PII workspace" : "PHI workspace";

  renderSubNav();
  showPanel(state.panel);
}

function renderSubNav() {
  const nav = $("#sub-nav");
  const items = NAV_CONFIG[state.category];
  nav.innerHTML = items
    .map(
      (item) =>
        `<button type="button" class="sub-nav-btn" data-panel="${item.panel}">${item.label}</button>`
    )
    .join("");

  nav.querySelectorAll(".sub-nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => showPanel(btn.dataset.panel));
  });
}

function showPanel(panelName) {
  state.panel = panelName;
  $all(".sub-nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.panel === panelName);
  });
  $all(".panel").forEach((panel) => {
    const match =
      panel.dataset.category === state.category && panel.dataset.panel === panelName;
    panel.classList.toggle("panel-active", match);
  });
}

$all(".category-card").forEach((card) => {
  card.addEventListener("click", () => openCategory(card.dataset.category));
});

$("#back-home-btn").addEventListener("click", showHome);

// ---------------------------------------------------------------------------
// Label / color helpers
// ---------------------------------------------------------------------------
const ENTITY_COLORS = {};
const PHI_LABELS = {};
const PII_PALETTE = ["#f94144", "#f3722c", "#577590", "#277da1", "#43aa8b", "#9d4edd"];
const PHI_PALETTE = ["#0d9488", "#0891b2", "#2563eb", "#7c3aed", "#c026d3", "#0f766e"];

function displayLabel(entity) {
  if (typeof entity === "string") {
    return PHI_LABELS[entity] || entity.replaceAll("_", " ");
  }
  return entity.label || PHI_LABELS[entity.entity] || entity.entity.replaceAll("_", " ");
}

function colorFor(entityName, category) {
  if (!ENTITY_COLORS[entityName]) {
    const palette = category === "phi" || PHI_LABELS[entityName] ? PHI_PALETTE : PII_PALETTE;
    ENTITY_COLORS[entityName] = palette[Object.keys(ENTITY_COLORS).length % palette.length];
  }
  return ENTITY_COLORS[entityName];
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function categoryBadge(category) {
  return `<span class="category-pill ${category}">${category.toUpperCase()}</span>`;
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

async function apiGet(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function renderHighlightedText(text, entities) {
  if (!entities.length) return `<span class="muted">${escapeHtml(text)}</span>`;
  const sorted = [...entities].sort((a, b) => a.start - b.start);
  let out = "";
  let cursor = 0;
  for (const ent of sorted) {
    out += escapeHtml(text.slice(cursor, ent.start));
    const color = colorFor(ent.entity, ent.category);
    const label = displayLabel(ent);
    out += `<mark style="background:${color}33;border-bottom:2px solid ${color}" title="${escapeHtml(label)} — ${(ent.confidence * 100).toFixed(1)}%">${escapeHtml(text.slice(ent.start, ent.end))}<span class="entity-tag" style="background:${color}">${escapeHtml(label)}</span></mark>`;
    cursor = ent.end;
  }
  out += escapeHtml(text.slice(cursor));
  return out;
}

function renderEntityTable(entities) {
  if (!entities.length) return "<p class='muted'>No entities found.</p>";
  const rows = entities
    .map((e) => {
      const color = colorFor(e.entity, e.category || "pii");
      const label = displayLabel(e);
      return `<tr>
        <td>${categoryBadge(e.category || "pii")}</td>
        <td><span class="entity-chip" style="background:${color}">${escapeHtml(label)}</span></td>
        <td><code class="entity-code">${escapeHtml(e.entity)}</code></td>
        <td>${escapeHtml(e.text)}</td>
        <td>${e.start}\u2013${e.end}</td>
        <td>${(e.confidence * 100).toFixed(1)}%</td>
      </tr>`;
    })
    .join("");
  return `<table><thead><tr><th>Cat</th><th>Label</th><th>Type</th><th>Text</th><th>Offset</th><th>Conf</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ---------------------------------------------------------------------------
// Copy to clipboard helpers
// ---------------------------------------------------------------------------
const copyStore = new Map();
let copyCounter = 0;
const copyTimeouts = new WeakMap();

function renderOutputBox(text, label = "Output", htmlContent = null) {
  const id = `copy_${++copyCounter}`;
  copyStore.set(id, text);
  const content = htmlContent !== null ? htmlContent : escapeHtml(text);
  const contentClass = htmlContent !== null ? "highlighted-text" : "masked-box";

  return `
    <div class="output-container" data-copy-id="${id}">
      <div class="output-header">
        <span class="output-title">${escapeHtml(label)}</span>
        <button type="button" class="copy-btn" data-copy-id="${id}" title="Copy to clipboard" aria-label="Copy to clipboard">
          <svg class="copy-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span class="copy-btn-text">Copy</span>
        </button>
      </div>
      <div class="${contentClass}">${content}</div>
    </div>
  `;
}

async function copyTextToClipboard(text, btn) {
  let ok = false;
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      ok = false;
    }
  }
  if (!ok) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      ta.style.left = "-9999px";
      ta.style.top = "-9999px";
      ta.setAttribute("readonly", "");
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      ok = document.execCommand("copy");
      document.body.removeChild(ta);
    } catch (e) {
      console.error("Copy fallback failed:", e);
      ok = false;
    }
  }

  if (ok) {
    if (copyTimeouts.has(btn)) {
      clearTimeout(copyTimeouts.get(btn));
    }
    btn.classList.add("copied");
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
      <span class="copy-btn-text">Copied!</span>
    `;
    const t = setTimeout(() => {
      btn.classList.remove("copied");
      btn.innerHTML = `
        <svg class="copy-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
        <span class="copy-btn-text">Copy</span>
      `;
      copyTimeouts.delete(btn);
    }, 2000);
    copyTimeouts.set(btn, t);
  }
}

document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".copy-btn");
  if (!btn) return;
  const id = btn.dataset.copyId;
  let text = copyStore.get(id);
  if (text === undefined) {
    const container = btn.closest(".output-container");
    if (container) {
      const box = container.querySelector(".masked-box, .highlighted-text");
      if (box) text = box.innerText || box.textContent;
    }
  }
  if (text !== undefined) {
    await copyTextToClipboard(text, btn);
  }
});


function renderPhiEntityCatalog(types) {
  const cards = types
    .map((t) => {
      const name = t.entity;
      const label = t.label || displayLabel(name);
      PHI_LABELS[name] = label;
      const desc = t.description ? `<span class="label-desc">${escapeHtml(t.description)}</span>` : "";
      return `<div class="entity-label-card" title="${escapeHtml(name)}">
        <span class="label-name">${escapeHtml(label)}</span>
        ${desc}
      </div>`;
    })
    .join("");
  return `<div class="entity-label-grid">${cards}</div>
    <div class="entity-count-bar">${types.length} PHI entity labels</div>`;
}

function renderPiiEntityCatalog(types) {
  const cards = types
    .map(
      (t) => `<div class="entity-label-card" title="${escapeHtml(t)}">
        <span class="label-name">${escapeHtml(t.replaceAll("_", " "))}</span>
      </div>`
    )
    .join("");
  return `<div class="entity-label-grid">${cards}</div>
    <div class="entity-count-bar">${types.length} PII entity types</div>`;
}

// ---------------------------------------------------------------------------
// Health + entity catalogs
// ---------------------------------------------------------------------------
async function checkHealth() {
  const badge = $("#health-badge");
  const phiBadge = $("#phi-health-badge");
  try {
    const health = await apiGet("/health");
    badge.textContent = health.model_loaded ? `PII ● Online` : "PII ● Degraded";
    badge.className = "badge " + (health.model_loaded ? "badge-ok" : "badge-warn");

    if (health.phi_ready) {
      phiBadge.textContent = `PHI ● Ready`;
      phiBadge.className = "badge badge-ok";
      phiBadge.title = `${health.phi_backend}${health.phi_model ? " · " + health.phi_model : ""}`;
    } else {
      phiBadge.textContent = "PHI ● Setup needed";
      phiBadge.className = "badge badge-warn";
      phiBadge.title = health.phi_detail || "Set OPENAI_API_KEY in .env";
    }
  } catch {
    badge.textContent = "PII ● Offline";
    badge.className = "badge badge-error";
    phiBadge.textContent = "PHI ● Offline";
    phiBadge.className = "badge badge-error";
  }
}

async function loadInfo() {
  try {
    const info = await apiGet("/info");
    $("#api-info").textContent = `${info.name} v${info.version}`;
  } catch {
    $("#api-info").textContent = "Service info unavailable";
  }
}

async function loadPiiEntities() {
  const container = $("#entities-result");
  const filter = $("#validate-entity-filter");
  try {
    const data = await apiGet("/entities");
    container.innerHTML = renderPiiEntityCatalog(data.entity_types);
    filter.innerHTML = data.entity_types
      .map((t) => `<label class="chip-checkbox"><input type="checkbox" value="${t}" />${escapeHtml(t.replaceAll("_", " "))}</label>`)
      .join("");
  } catch (e) {
    container.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function loadPhiEntities() {
  const container = $("#phi-entities-result");
  const filter = $("#phi-validate-entity-filter");
  try {
    const data = await apiGet("/phi/entities");
    container.innerHTML = renderPhiEntityCatalog(data.entity_types);
    filter.innerHTML = data.entity_types
      .map((t) => {
        PHI_LABELS[t.entity] = t.label;
        return `<label class="chip-checkbox"><input type="checkbox" value="${t.entity}" />${escapeHtml(t.label)}</label>`;
      })
      .join("");
  } catch (e) {
    container.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

// ---------------------------------------------------------------------------
// PII actions
// ---------------------------------------------------------------------------
$("#predict-confidence").addEventListener("input", (e) => {
  $("#predict-confidence-val").textContent = parseFloat(e.target.value).toFixed(2);
});

$("#predict-btn").addEventListener("click", async () => {
  const text = $("#predict-text").value;
  const el = $("#predict-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Detecting…</p>";
  try {
    const data = await apiPost("/predict", {
      text,
      min_confidence: parseFloat($("#predict-confidence").value),
    });
    el.innerHTML = `
      ${renderOutputBox(data.text, "Detected entities", renderHighlightedText(data.text, data.entities))}
      <p class="summary ${data.contains_pii ? "bad" : "good"}">${data.contains_pii ? `${data.entity_count} entities found` : "No PII detected"}</p>
      ${renderEntityTable(data.entities)}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#validate-btn").addEventListener("click", async () => {
  const text = $("#validate-text").value;
  const el = $("#validate-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Validating…</p>";
  const entity_types = [...$all("#validate-entity-filter input:checked")].map((i) => i.value);
  try {
    const data = await apiPost("/validate", { text, entity_types });
    el.innerHTML = `
      <p class="summary ${data.contains_pii ? "bad" : "good"}">${data.contains_pii ? "Contains PII" : "Clean"}</p>
      ${renderEntityTable(data.entities)}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#mask-btn").addEventListener("click", async () => {
  const text = $("#mask-text").value;
  const el = $("#mask-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Masking…</p>";
  try {
    const data = await apiPost("/mask", { text, mask_style: $("#mask-style").value });
    el.innerHTML = `
      ${renderOutputBox(data.masked_text, "Masked text")}
      ${renderEntityTable(data.entities)}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#batch-btn").addEventListener("click", async () => {
  const texts = $("#batch-text").value.split("\n").map((t) => t.trim()).filter(Boolean);
  const el = $("#batch-result");
  if (!texts.length) return (el.innerHTML = "<p class='error'>Add at least one line.</p>");
  el.innerHTML = "<p class='muted'>Running batch…</p>";
  try {
    const data = await apiPost("/predict/batch", { texts });
    el.innerHTML = data.results
      .map(
        (r, i) => `<div class="batch-item">
          ${renderOutputBox(r.text, `#${i + 1} — ${r.entity_count} entities`, renderHighlightedText(r.text, r.entities))}
        </div>`
      )
      .join("");
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#nav-tokens-btn").addEventListener("click", () => window.open("/admin/tokens", "_blank"));

$("#anonymize-btn").addEventListener("click", async () => {
  const text = $("#anonymize-text").value;
  const el = $("#anonymize-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Anonymizing…</p>";
  try {
    const headers = { "Content-Type": "application/json", "x-direction": "external" };
    const preset = $("#anonymize-preset-select").value;
    if (preset) headers["x-policy-preset"] = preset;
    const res = await fetch("/api/v1/anonymize", { method: "POST", headers, body: JSON.stringify({ text }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Request failed");
    let mappingsHtml = "";
    if (data.mappings?.length) {
      mappingsHtml = `<table><thead><tr><th>Type</th><th>Original</th><th>Token</th><th>Policy</th></tr></thead><tbody>${data.mappings
        .map(
          (m) => `<tr>
            <td><code class="entity-code">${escapeHtml(m.entity_type)}</code></td>
            <td>${escapeHtml(m.original_value)}</td>
            <td><code>${escapeHtml(m.tokenized_value)}</code></td>
            <td>${escapeHtml(m.policy_applied || "—")}</td>
          </tr>`
        )
        .join("")}</tbody></table>`;
    }
    el.innerHTML = `
      ${renderOutputBox(data.anonymized_text, "Anonymized text")}
      ${mappingsHtml}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

// ---------------------------------------------------------------------------
// PHI actions
// ---------------------------------------------------------------------------
$("#phi-predict-confidence").addEventListener("input", (e) => {
  $("#phi-predict-confidence-val").textContent = parseFloat(e.target.value).toFixed(2);
});

$("#phi-predict-btn").addEventListener("click", async () => {
  const text = $("#phi-predict-text").value;
  const el = $("#phi-predict-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Detecting PHI…</p>";
  try {
    const data = await apiPost("/phi/predict", {
      text,
      min_confidence: parseFloat($("#phi-predict-confidence").value),
    });
    el.innerHTML = `
      <p class="hint">Backend: <code>${escapeHtml(data.backend)}</code></p>
      ${renderOutputBox(data.text, "Detected PHI", renderHighlightedText(data.text, data.entities))}
      <p class="summary ${data.contains_phi ? "bad" : "good"}">${data.contains_phi ? `${data.entity_count} PHI entities` : "No PHI detected"}</p>
      ${renderEntityTable(data.entities)}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#phi-validate-btn").addEventListener("click", async () => {
  const text = $("#phi-validate-text").value;
  const el = $("#phi-validate-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Validating…</p>";
  const entity_types = [...$all("#phi-validate-entity-filter input:checked")].map((i) => i.value);
  try {
    const data = await apiPost("/phi/validate", { text, entity_types });
    el.innerHTML = `
      <p class="summary ${data.contains_phi ? "bad" : "good"}">${data.contains_phi ? "Contains PHI" : "Clean"}</p>
      ${renderEntityTable(data.entities)}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#phi-mask-btn").addEventListener("click", async () => {
  const text = $("#phi-mask-text").value;
  const el = $("#phi-mask-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Masking…</p>";
  try {
    const data = await apiPost("/phi/mask", { text, mask_style: $("#phi-mask-style").value });
    el.innerHTML = `
      ${renderOutputBox(data.masked_text, "Masked text")}
      ${renderEntityTable(data.entities)}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#phi-batch-btn").addEventListener("click", async () => {
  const texts = $("#phi-batch-text").value.split("\n").map((t) => t.trim()).filter(Boolean);
  const el = $("#phi-batch-result");
  if (!texts.length) return (el.innerHTML = "<p class='error'>Add at least one line.</p>");
  el.innerHTML = "<p class='muted'>Running PHI batch…</p>";
  try {
    const data = await apiPost("/phi/predict/batch", { texts });
    el.innerHTML = data.results
      .map(
        (r, i) => `<div class="batch-item">
          ${renderOutputBox(r.text, `#${i + 1} — ${r.entity_count} PHI entities`, renderHighlightedText(r.text, r.entities))}
        </div>`
      )
      .join("");
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

$("#phi-nav-tokens-btn").addEventListener("click", () => window.open("/admin/tokens", "_blank"));

$("#phi-anonymize-btn").addEventListener("click", async () => {
  const text = $("#phi-anonymize-text").value;
  const el = $("#phi-anonymize-result");
  if (!text.trim()) return (el.innerHTML = "<p class='error'>Enter text first.</p>");
  el.innerHTML = "<p class='muted'>Anonymizing PHI…</p>";
  try {
    const data = await apiPost("/phi/anonymize", { text });
    let mappingsHtml = "";
    if (data.mappings?.length) {
      mappingsHtml = `<table><thead><tr><th>Label</th><th>Original</th><th>Redacted</th></tr></thead><tbody>${data.mappings
        .map(
          (m) => `<tr>
            <td>${escapeHtml(m.label || m.entity_type)}</td>
            <td>${escapeHtml(m.original_value)}</td>
            <td><code>${escapeHtml(m.tokenized_value)}</code></td>
          </tr>`
        )
        .join("")}</tbody></table>`;
    }
    el.innerHTML = `
      ${renderOutputBox(data.anonymized_text, "Anonymized text")}
      ${mappingsHtml}`;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
});

// ---------------------------------------------------------------------------
// Inits
// ---------------------------------------------------------------------------
showHome();
checkHealth();
loadInfo();
loadPiiEntities();
loadPhiEntities();
setInterval(checkHealth, 30000);
