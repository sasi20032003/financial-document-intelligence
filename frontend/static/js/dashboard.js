const elements = {
  body: document.querySelector("#documents-body"),
  emptyState: document.querySelector("#empty-state"),
  emptyTitle: document.querySelector("#empty-title"),
  emptyCopy: document.querySelector("#empty-copy"),
  search: document.querySelector("#search"),
  typeFilter: document.querySelector("#type-filter"),
  statusFilter: document.querySelector("#status-filter"),
  form: document.querySelector("#upload-form"),
  fileInput: document.querySelector("#document-file"),
  fileLabel: document.querySelector("#file-label"),
  fileMeta: document.querySelector("#file-meta"),
  fileSelection: document.querySelector("#file-selection"),
  dropzone: document.querySelector("#dropzone"),
  message: document.querySelector("#upload-message"),
  button: document.querySelector("#process-button"),
  typeBreakdown: document.querySelector("#type-breakdown"),
  breakdownEmpty: document.querySelector("#breakdown-empty"),
  activityList: document.querySelector("#activity-list"),
  activityEmpty: document.querySelector("#activity-empty"),
  mobileMenu: document.querySelector("#mobile-menu"),
  sidebar: document.querySelector("#sidebar"),
  scrim: document.querySelector("#mobile-scrim"),
  datasetButton: document.querySelector("#dataset-process-button"),
  datasetSummary: document.querySelector("#dataset-summary"),
  datasetCount: document.querySelector("#dataset-count"),
  datasetProgress: document.querySelector("#dataset-progress"),
  datasetProgressLabel: document.querySelector("#dataset-progress-label"),
  datasetProgressCount: document.querySelector("#dataset-progress-count"),
  datasetProgressBar: document.querySelector("#dataset-progress-bar"),
  datasetCurrentFile: document.querySelector("#dataset-current-file"),
  datasetWarning: document.querySelector("#dataset-warning"),
  datasetMessage: document.querySelector("#dataset-message"),
};

const state = {
  documents: [],
  total: 0,
  dataset: null,
  datasetRunning: false,
  datasetCancelRequested: false,
  providerConfigured: null,
};

const typeDetails = {
  invoice: { label: "Invoice", short: "INV", color: "blue" },
  balance_sheet: { label: "Balance sheet", short: "BS", color: "violet" },
  profit_and_loss: { label: "Profit & loss", short: "P&L", color: "green" },
  cash_flow_statement: { label: "Cash flow", short: "CF", color: "amber" },
};

const typeDetail = (value) => typeDetails[value] || {
  label: String(value || "Document").replaceAll("_", " "),
  short: "DOC",
  color: "slate",
};

const createElement = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const createSvg = (path) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const pathNode = document.createElementNS("http://www.w3.org/2000/svg", "path");
  pathNode.setAttribute("d", path);
  svg.append(pathNode);
  return svg;
};

const badge = (text, kind) => {
  const value = createElement("span", "badge " + kind, text);
  return value;
};

const cell = (content, className) => {
  const td = createElement("td", className);
  if (content instanceof Node) td.append(content);
  else td.textContent = content;
  return td;
};

const documentState = (item) => {
  if (item.processing_status !== "PASS") return "failed";
  if (item.validation_status === "FAIL") return "review";
  return "ready";
};

const confidenceValue = (value) => {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Math.max(0, Math.min(100, Math.round(Number(value) * 100)));
};

const formatDate = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  }).format(date);
};

const relativeTime = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const ranges = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of ranges) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit);
  }
  return "just now";
};

function createDocumentCell(item) {
  const details = typeDetail(item.document_type);
  const wrapper = createElement("div", "document-identity");
  const icon = createElement("span", "file-tile " + details.color, details.short);
  const copy = createElement("span", "document-copy");
  const link = createElement("a", "document-link", item.document_name);
  link.href = "/results?name=" + encodeURIComponent(item.document_name);
  const subtitle = createElement("small", null, details.label);
  copy.append(link, subtitle);
  wrapper.append(icon, copy);
  return wrapper;
}

function createStatusCell(item) {
  const status = documentState(item);
  const copy = {
    ready: "Ready",
    review: "Review",
    failed: "Failed",
  }[status];
  return badge(copy, status);
}

function createConfidenceCell(item) {
  const confidence = confidenceValue(item.overall_confidence);
  const wrapper = createElement("div", "confidence-cell");
  wrapper.append(createElement("strong", null, confidence == null ? "-" : confidence + "%"));
  const track = createElement("span", "confidence-track");
  const fill = createElement("i");
  fill.style.width = (confidence == null ? 0 : confidence) + "%";
  track.append(fill);
  wrapper.append(track);
  return wrapper;
}

function createValidationCell(item) {
  const status = item.validation_status || "NOT_APPLICABLE";
  const labels = {
    PASS: "Passed",
    FAIL: "Exception",
    NOT_APPLICABLE: "N/A",
  };
  const kinds = {
    PASS: "pass",
    FAIL: "fail",
    NOT_APPLICABLE: "not-applicable",
  };
  return badge(labels[status] || status, kinds[status] || "neutral");
}

function createAction(item) {
  const link = createElement("a", "row-action");
  link.href = "/results?name=" + encodeURIComponent(item.document_name);
  link.setAttribute("aria-label", "View " + item.document_name);
  link.append(createSvg("m9 5 7 7-7 7"));
  return link;
}

function filteredDocuments() {
  const query = elements.search.value.trim().toLowerCase();
  const type = elements.typeFilter.value;
  const status = elements.statusFilter.value;
  return state.documents.filter((item) => {
    const details = typeDetail(item.document_type);
    const searchable = [
      item.document_name,
      details.label,
      item.processing_status,
      item.validation_status,
    ].join(" ").toLowerCase();
    return (!query || searchable.includes(query))
      && (type === "all" || item.document_type === type)
      && (status === "all" || documentState(item) === status);
  });
}

function renderRows() {
  const items = filteredDocuments();
  elements.body.replaceChildren();

  items.forEach((item) => {
    const row = document.createElement("tr");
    row.append(
      cell(createDocumentCell(item)),
      cell(createStatusCell(item)),
      cell(createConfidenceCell(item)),
      cell(createValidationCell(item)),
      cell(formatDate(item.processed_at), "date-cell"),
      cell(createAction(item), "action-cell"),
    );
    elements.body.append(row);
  });

  const hasFilters = elements.search.value.trim()
    || elements.typeFilter.value !== "all"
    || elements.statusFilter.value !== "all";
  elements.emptyState.hidden = items.length > 0;
  document.querySelector(".dashboard-table-wrap").hidden = items.length === 0;
  if (state.documents.length === 0) {
    elements.emptyTitle.textContent = "No documents yet";
    elements.emptyCopy.textContent = "Upload a financial document to create your first extraction.";
  } else if (hasFilters) {
    elements.emptyTitle.textContent = "No matching documents";
    elements.emptyCopy.textContent = "Try changing the search term or selected filters.";
  }
  document.querySelector("#record-count").textContent = items.length + (items.length === 1 ? " record" : " records");
  document.querySelector("#table-summary").textContent = "Showing " + items.length + " of " + state.documents.length + " documents";
}

function renderStats() {
  const successful = state.documents.filter((item) => item.processing_status === "PASS").length;
  const review = state.documents.filter((item) => documentState(item) === "review").length;
  const rate = state.documents.length ? Math.round((successful / state.documents.length) * 100) : null;

  document.querySelector("#stat-total").textContent = state.total.toLocaleString();
  document.querySelector("#stat-pass").textContent = successful.toLocaleString();
  document.querySelector("#stat-review").textContent = review.toLocaleString();
  document.querySelector("#stat-rate").textContent = rate == null ? "-" : rate + "%";
  document.querySelector("#success-progress").style.width = (rate || 0) + "%";
  document.querySelector("#nav-total").textContent = state.total.toLocaleString();
  document.querySelector("#nav-review").textContent = review.toLocaleString();

  document.querySelector("#total-context").textContent = state.total
    ? "Stored in the processing workspace"
    : "No documents processed yet";
  document.querySelector("#pass-context").textContent = successful
    ? successful + (successful === 1 ? " extraction completed" : " extractions completed")
    : "Waiting for first extraction";
  document.querySelector("#review-context").textContent = review
    ? review + (review === 1 ? " validation exception" : " validation exceptions")
    : "No validation exceptions";
}

function renderBreakdown() {
  elements.typeBreakdown.replaceChildren();
  if (state.documents.length === 0) {
    elements.breakdownEmpty.hidden = false;
    return;
  }
  elements.breakdownEmpty.hidden = true;
  const counts = Object.fromEntries(Object.keys(typeDetails).map((key) => [key, 0]));
  state.documents.forEach((item) => {
    counts[item.document_type] = (counts[item.document_type] || 0) + 1;
  });
  const max = Math.max(...Object.values(counts), 1);

  Object.entries(typeDetails).forEach(([key, details]) => {
    const count = counts[key] || 0;
    const row = createElement("div", "breakdown-row");
    const label = createElement("div", "breakdown-label");
    label.append(
      createElement("span", "breakdown-dot " + details.color),
      createElement("strong", null, details.label),
      createElement("span", null, count.toString()),
    );
    const track = createElement("div", "breakdown-track");
    const fill = createElement("span", details.color);
    fill.style.width = Math.round((count / max) * 100) + "%";
    track.append(fill);
    row.append(label, track);
    elements.typeBreakdown.append(row);
  });
}

function renderActivity() {
  elements.activityList.replaceChildren();
  const items = state.documents.slice(0, 4);
  elements.activityEmpty.hidden = items.length > 0;
  if (!items.length) return;

  items.forEach((item) => {
    const status = documentState(item);
    const row = createElement("div", "activity-row");
    const dot = createElement("span", "activity-dot " + status);
    const copy = createElement("div", "activity-copy");
    const description = status === "ready"
      ? "Extraction completed"
      : status === "review"
        ? "Validation exception detected"
        : "Processing failed";
    copy.append(
      createElement("strong", null, description),
      createElement("span", null, item.document_name),
    );
    row.append(dot, copy, createElement("time", null, relativeTime(item.processed_at)));
    elements.activityList.append(row);
  });
}

function renderDashboard() {
  renderStats();
  renderRows();
  renderBreakdown();
  renderActivity();
}

async function loadDocuments() {
  try {
    const response = await fetch("/api/v1/documents?limit=200");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "Could not load documents.");
    state.documents = Array.isArray(payload.items) ? payload.items : [];
    state.total = Number(payload.total || state.documents.length);
    renderDashboard();
  } catch (error) {
    elements.message.className = "form-message error";
    elements.message.textContent = error.message;
    state.documents = [];
    state.total = 0;
    renderDashboard();
  }
}

function renderDatasetStatus() {
  const manifest = state.dataset;
  if (!manifest) return;
  if (!manifest.available) {
    elements.datasetSummary.textContent = "Local dataset folder is unavailable";
    elements.datasetCount.textContent = "0 files";
    elements.datasetButton.disabled = true;
    elements.datasetButton.querySelector("span").textContent = "Dataset not found";
    elements.datasetWarning.hidden = true;
    return;
  }

  const typeCount = new Set(manifest.items.map((item) => item.document_type)).size;
  elements.datasetSummary.textContent = manifest.total
    ? manifest.total + " supported files across " + typeCount + " folders"
    : "No supported files detected";
  elements.datasetCount.textContent = manifest.processed + " / " + manifest.total;

  const needsProvider = state.providerConfigured === false && manifest.remaining > 0;
  if (!state.datasetRunning) {
    elements.datasetButton.disabled = manifest.remaining === 0 || needsProvider;
    if (needsProvider) {
      elements.datasetButton.querySelector("span").textContent = "Configure Gemini to process";
    } else {
      elements.datasetButton.querySelector("span").textContent = manifest.remaining
        ? "Process " + manifest.remaining + " remaining files"
        : "Dataset is up to date";
    }
    elements.datasetButton.classList.remove("is-running");
  }

  if (needsProvider) {
    elements.datasetWarning.hidden = false;
    elements.datasetWarning.textContent =
      "This dataset contains scanned documents. Add GEMINI_API_KEY, then restart the app.";
  } else {
    elements.datasetWarning.hidden = true;
    elements.datasetWarning.textContent = "";
  }
}

async function loadHealth() {
  const topStatus = document.querySelector("#health-status");
  const sidebarDot = document.querySelector("#sidebar-health-dot");
  const sidebarCopy = document.querySelector("#sidebar-health-copy");
  try {
    const response = await fetch("/api/v1/health");
    const health = await response.json();
    if (!response.ok || health.status !== "ok") throw new Error("Health check failed");
    state.providerConfigured = Boolean(health.extraction_provider_configured);
    if (health.extraction_provider_configured) {
      topStatus.className = "live-status healthy";
      topStatus.querySelector("span").textContent = "All systems operational";
      sidebarDot.className = "health-dot healthy";
      sidebarCopy.textContent = "API, database, and AI online";
    } else {
      topStatus.className = "live-status warning";
      topStatus.querySelector("span").textContent = "Provider setup needed";
      sidebarDot.className = "health-dot warning";
      sidebarCopy.textContent = "API online - AI key required";
    }
  } catch {
    state.providerConfigured = false;
    topStatus.className = "live-status offline";
    topStatus.querySelector("span").textContent = "Service unavailable";
    sidebarDot.className = "health-dot offline";
    sidebarCopy.textContent = "Unable to reach the API";
  }
  renderDatasetStatus();
}

async function loadDataset() {
  try {
    const response = await fetch("/api/v1/dataset");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "Could not scan the dataset.");
    state.dataset = payload;
    renderDatasetStatus();
  } catch (error) {
    state.dataset = {
      available: false,
      total: 0,
      processed: 0,
      remaining: 0,
      items: [],
    };
    renderDatasetStatus();
    elements.datasetMessage.className = "dataset-message error";
    elements.datasetMessage.textContent = error.message;
  }
}

function updateDatasetProgress(index, total, filename) {
  const completed = Math.min(index, total);
  const percent = total ? Math.round((completed / total) * 100) : 0;
  elements.datasetProgress.hidden = false;
  elements.datasetProgressLabel.textContent = state.datasetCancelRequested
    ? "Stopping after current file"
    : "Processing dataset";
  elements.datasetProgressCount.textContent = completed + " / " + total;
  elements.datasetProgressBar.style.width = percent + "%";
  elements.datasetCurrentFile.textContent = filename || "Preparing next document";
}

async function processDataset() {
  if (state.datasetRunning) {
    state.datasetCancelRequested = true;
    elements.datasetButton.disabled = true;
    elements.datasetButton.querySelector("span").textContent = "Stopping...";
    elements.datasetProgressLabel.textContent = "Stopping after current file";
    return;
  }

  const pending = (state.dataset?.items || []).filter(
    (item) => !item.already_processed
  );
  if (!pending.length) return;

  state.datasetRunning = true;
  state.datasetCancelRequested = false;
  elements.datasetMessage.textContent = "";
  elements.datasetMessage.className = "dataset-message";
  elements.datasetButton.disabled = false;
  elements.datasetButton.classList.add("is-running");
  elements.datasetButton.querySelector("span").textContent = "Stop after current file";

  let successful = 0;
  let failed = 0;
  updateDatasetProgress(0, pending.length, "Preparing first document");

  for (let index = 0; index < pending.length; index += 1) {
    if (state.datasetCancelRequested) break;
    const item = pending[index];
    updateDatasetProgress(index, pending.length, item.document_name);
    try {
      const response = await fetch("/api/v1/dataset/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ relative_path: item.relative_path }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error?.message || "Processing failed.");
      }
      successful += 1;
    } catch {
      failed += 1;
    }
    updateDatasetProgress(index + 1, pending.length, item.document_name);
  }

  const stopped = state.datasetCancelRequested;
  state.datasetRunning = false;
  state.datasetCancelRequested = false;
  elements.datasetMessage.className = failed ? "dataset-message warning" : "dataset-message success";
  elements.datasetMessage.textContent = stopped
    ? "Batch stopped. " + successful + " completed and " + failed + " failed."
    : "Batch finished. " + successful + " completed and " + failed + " failed.";
  await Promise.all([loadDocuments(), loadDataset()]);
}

function updateFileSelection(file) {
  if (!file) {
    elements.dropzone.classList.remove("has-file");
    elements.fileSelection.hidden = true;
    elements.fileLabel.textContent = "";
    elements.fileMeta.textContent = "";
    return;
  }
  const size = file.size < 1024 * 1024
    ? Math.max(1, Math.round(file.size / 1024)) + " KB"
    : (file.size / (1024 * 1024)).toFixed(1) + " MB";
  elements.fileLabel.textContent = file.name;
  elements.fileMeta.textContent = size + "  -  Ready to process";
  elements.fileSelection.hidden = false;
  elements.dropzone.classList.add("has-file");
}

function setMobileMenu(open) {
  document.body.classList.toggle("menu-open", open);
  elements.mobileMenu.setAttribute("aria-expanded", String(open));
  elements.scrim.hidden = !open;
}

[elements.search, elements.typeFilter, elements.statusFilter].forEach((control) => {
  control.addEventListener(control === elements.search ? "input" : "change", renderRows);
});

document.querySelector("#review-nav").addEventListener("click", () => {
  elements.statusFilter.value = "review";
  renderRows();
  setMobileMenu(false);
});

elements.fileInput.addEventListener("change", () => {
  updateFileSelection(elements.fileInput.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.remove("is-dragging");
  });
});

elements.dropzone.addEventListener("drop", (event) => {
  const files = event.dataTransfer?.files;
  if (!files?.length) return;
  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  elements.fileInput.files = transfer.files;
  updateFileSelection(files[0]);
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.message.textContent = "";
  elements.message.className = "form-message";
  elements.button.disabled = true;
  elements.button.classList.add("is-processing");
  elements.button.querySelector("span").textContent = "Processing document";
  const data = new FormData(elements.form);
  try {
    const response = await fetch("/api/v1/documents/process", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "Processing failed.");
    window.location.assign("/results?name=" + encodeURIComponent(payload.document_name));
  } catch (error) {
    elements.message.className = "form-message error";
    elements.message.textContent = error.message;
    elements.button.disabled = false;
    elements.button.classList.remove("is-processing");
    elements.button.querySelector("span").textContent = "Process document";
    loadDocuments();
  }
});

elements.datasetButton.addEventListener("click", processDataset);

elements.mobileMenu.addEventListener("click", () => {
  setMobileMenu(!document.body.classList.contains("menu-open"));
});
elements.scrim.addEventListener("click", () => setMobileMenu(false));
window.addEventListener("resize", () => {
  if (window.innerWidth > 980) setMobileMenu(false);
});

document.querySelector("#current-date").textContent = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
}).format(new Date());

loadHealth();
loadDocuments();
loadDataset();
