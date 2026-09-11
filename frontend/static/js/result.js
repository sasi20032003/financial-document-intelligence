const params = new URLSearchParams(window.location.search);
const name = params.get("name");
const message = document.querySelector("#result-message");

const text = (tag, value, className) => {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
};

const badge = (value) => text("span", value, "badge " + String(value).toLowerCase().replaceAll("_", "-"));

const formatValue = (value) => {
  if (value === null || value === undefined || value === "") return "Missing / unreadable";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
};

function renderFields(data) {
  const target = document.querySelector("#fields-content");
  if (!data.fields.length) {
    target.append(text("p", "No fields were extracted.", "empty-copy"));
    return;
  }
  const groups = new Map();
  data.fields.forEach((field) => {
    const group = field.period || field.section || "Document";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(field);
  });
  groups.forEach((fields, group) => {
    target.append(text("h3", group));
    const table = document.createElement("table");
    table.className = "fields-table";
    table.innerHTML = "<thead><tr><th>Field</th><th>Value</th><th>Evidence</th><th>Confidence</th></tr></thead>";
    const tbody = document.createElement("tbody");
    fields.forEach((field) => {
      const row = document.createElement("tr");
      if (field.value === null) row.className = "missing-row";
      const fieldCell = document.createElement("td");
      fieldCell.append(text("strong", field.label), text("small", field.key));
      const evidence = document.createElement("td");
      evidence.append(text("span", field.evidence.source_text || "No source text"));
      if (field.evidence.page_number) evidence.append(text("small", "Page " + field.evidence.page_number));
      [fieldCell, text("td", formatValue(field.value)), evidence, text("td", field.confidence == null ? "-" : Math.round(field.confidence * 100) + "%")].forEach((node) => row.append(node));
      tbody.append(row);
    });
    table.append(tbody);
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    wrap.append(table);
    target.append(wrap);
  });
}

function renderTables(tables) {
  const target = document.querySelector("#tables-content");
  if (!tables.length) {
    target.append(text("p", "No tables were detected.", "empty-copy"));
    return;
  }
  tables.forEach((sourceTable) => {
    const heading = text("h3", sourceTable.title || sourceTable.name);
    if (sourceTable.page_number) heading.append(text("small", "Page " + sourceTable.page_number));
    target.append(heading);
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    sourceTable.columns.forEach((column) => headRow.append(text("th", column)));
    thead.append(headRow);
    const tbody = document.createElement("tbody");
    sourceTable.rows.forEach((values) => {
      const row = document.createElement("tr");
      sourceTable.columns.forEach((_, index) => row.append(text("td", formatValue(values[index]))));
      tbody.append(row);
    });
    table.append(thead, tbody);
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    wrap.append(table);
    target.append(wrap);
  });
}

function renderValidations(validation) {
  const target = document.querySelector("#validations-content");
  target.append(badge(validation.overall_status));
  const grid = document.createElement("div");
  grid.className = "validation-grid";
  validation.checks.forEach((check) => {
    const card = document.createElement("article");
    card.className = "validation-card " + check.status.toLowerCase().replaceAll("_", "-");
    const header = document.createElement("div");
    header.append(text("h3", check.name.replaceAll("_", " ")), badge(check.status));
    card.append(header, text("p", check.formula, "formula"));
    if (check.period) card.append(text("p", "Period: " + check.period, "muted"));
    const values = document.createElement("dl");
    [["Calculated", check.calculated_value], ["Reported", check.reported_value], ["Variance", check.variance]].forEach(([label, value]) => {
      const group = document.createElement("div");
      group.append(text("dt", label), text("dd", formatValue(value)));
      values.append(group);
    });
    card.append(values);
    if (check.notes) card.append(text("p", check.notes, "validation-note"));
    grid.append(card);
  });
  target.append(grid);
}

function renderOverview(payload) {
  const target = document.querySelector("#overview");
  const items = [
    ["Fields", payload.extracted_data.fields.length],
    ["Tables", payload.extracted_data.tables.length],
    ["Pages", payload.file_validation.page_count ?? "-"],
    ["Processing time", payload.processing_metadata.processing_time_ms + " ms"],
  ];
  items.forEach(([label, value]) => {
    const article = document.createElement("article");
    article.append(text("span", label), text("strong", value));
    target.append(article);
  });
}

async function loadResult() {
  if (!name) {
    message.className = "form-message error";
    message.textContent = "No document name was supplied.";
    return;
  }
  try {
    const response = await fetch("/api/v1/documents/" + encodeURIComponent(name));
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "Could not load the result.");
    document.title = payload.document_name + "  -  Document Intelligence";
    document.querySelector("#document-name").textContent = payload.document_name;
    const meta = document.querySelector("#result-meta");
    meta.append(
      badge(payload.processing_status),
      badge(payload.validation.overall_status),
      text("span", payload.document_type.replaceAll("_", " ")),
      text("span", new Date(payload.processing_metadata.processed_at).toLocaleString()),
    );
    renderOverview(payload);
    renderFields(payload.extracted_data);
    renderTables(payload.extracted_data.tables);
    renderValidations(payload.validation);
    document.querySelector("#json-content").textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    message.className = "form-message error";
    message.textContent = error.message;
  }
}

document.querySelector("#copy-json").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(document.querySelector("#json-content").textContent);
  event.currentTarget.textContent = "Copied";
  setTimeout(() => event.currentTarget.textContent = "Copy JSON", 1200);
});

loadResult();
