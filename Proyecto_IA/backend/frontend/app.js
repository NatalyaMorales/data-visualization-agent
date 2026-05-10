const API_URL = "";

let currentProfile = [];
let currentFile = null;
let currentRecommendations = [];
let allRecommendationColumns = [];
let allChartTypes = [];

let includeColumnFilter = [];
let chartTypeFilter = [];

// =============================
// ELEMENTOS
// =============================
const fileInput = document.getElementById("fileInput");
const separatorInput = document.getElementById("separator");
const encodingInput = document.getElementById("encoding");
const profileBtn = document.getElementById("profileBtn");
const processBtn = document.getElementById("processBtn");
const dashboardBtn = document.getElementById("dashboardBtn");
const reportBtn = document.getElementById("reportBtn");

const nullThresholdInput = document.getElementById("nullThreshold");
const audienceInput = document.getElementById("audience");
const removeHighNullColsInput = document.getElementById("removeHighNullCols");
const skipNullRemovalInput = document.getElementById("skipNullRemoval");
const nullStrategyInput = document.getElementById("nullStrategy");

const summaryDiv = document.getElementById("summary");
const profileContainer = document.getElementById("profileContainer");
const recommendationsDiv = document.getElementById("recommendations");

const includeFilterBtn = document.getElementById("includeFilterBtn");
const includeFilterPanel = document.getElementById("includeFilterPanel");
const includeFilterSearch = document.getElementById("includeFilterSearch");
const includeFilterOptions = document.getElementById("includeFilterOptions");
const includeSelectAllBtn = document.getElementById("includeSelectAllBtn");
const includeClearBtn = document.getElementById("includeClearBtn");

const chartTypeFilterBtn = document.getElementById("chartTypeFilterBtn");
const chartTypeFilterPanel = document.getElementById("chartTypeFilterPanel");
const chartTypeFilterSearch = document.getElementById("chartTypeFilterSearch");
const chartTypeFilterOptions = document.getElementById("chartTypeFilterOptions");
const chartTypeSelectAllBtn = document.getElementById("chartTypeSelectAllBtn");
const chartTypeClearBtn = document.getElementById("chartTypeClearBtn");

// =============================
// EVENTOS
// =============================
profileBtn.addEventListener("click", perfilDataset);
processBtn.addEventListener("click", procesarDataset);
dashboardBtn.addEventListener("click", generarDashboard);

if (reportBtn) {
  reportBtn.addEventListener("click", generarReporte);
}

includeFilterBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  togglePanel(includeFilterPanel, chartTypeFilterPanel);
});

chartTypeFilterBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  togglePanel(chartTypeFilterPanel, includeFilterPanel);
});

includeFilterSearch.addEventListener("input", () => {
  renderSingleFilterOptions("include");
});

chartTypeFilterSearch.addEventListener("input", () => {
  renderSingleFilterOptions("chartType");
});

includeSelectAllBtn.addEventListener("click", () => {
  includeColumnFilter = [...allRecommendationColumns];
  renderSingleFilterOptions("include");
  updateFilterButtonLabels();
  renderRecommendations(getFilteredRecommendations());
});

chartTypeSelectAllBtn.addEventListener("click", () => {
  chartTypeFilter = [...allChartTypes];
  renderSingleFilterOptions("chartType");
  updateFilterButtonLabels();
  renderRecommendations(getFilteredRecommendations());
});

includeClearBtn.addEventListener("click", () => {
  includeColumnFilter = [];
  renderSingleFilterOptions("include");
  updateFilterButtonLabels();
  renderRecommendations(getFilteredRecommendations());
});

chartTypeClearBtn.addEventListener("click", () => {
  chartTypeFilter = [];
  renderSingleFilterOptions("chartType");
  updateFilterButtonLabels();
  renderRecommendations(getFilteredRecommendations());
});

document.addEventListener("click", (event) => {
  const clickedInsideInclude =
    includeFilterPanel.contains(event.target) || includeFilterBtn.contains(event.target);

  const clickedInsideChartType =
    chartTypeFilterPanel.contains(event.target) || chartTypeFilterBtn.contains(event.target);

  if (!clickedInsideInclude) {
    includeFilterPanel.classList.add("hidden");
  }

  if (!clickedInsideChartType) {
    chartTypeFilterPanel.classList.add("hidden");
  }
});

// =============================
// PERFILAR DATASET
// =============================
async function perfilDataset() {
  currentFile = fileInput.files[0];

  if (!currentFile) {
    alert("Selecciona un archivo CSV.");
    return;
  }

  const formData = new FormData();
  formData.append("file", currentFile);
  formData.append("separator", normalizeSeparator(separatorInput.value));
  formData.append("encoding", encodingInput.value);

  try {
    const res = await fetch(`${API_URL}/api/profile`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || "No se pudo perfilar el dataset.");
    }

    currentProfile = data.profile || [];
    currentRecommendations = [];
    allRecommendationColumns = [];
    allChartTypes = [];
    includeColumnFilter = [];
    chartTypeFilter = [];

    summaryDiv.innerHTML = `
      <p><strong>Filas:</strong> ${data.rows}</p>
      <p><strong>Columnas:</strong> ${data.columns}</p>
    `;

    renderProfileTable(currentProfile);
    renderFilterOptions();
    updateFilterButtonLabels();

    recommendationsDiv.innerHTML = `<p class="empty-state">Aún no se han generado recomendaciones.</p>`;
  } catch (error) {
    console.error(error);
    alert(`Error al perfilar el dataset: ${error.message}`);
  }
}

// =============================
// PROCESAR DATASET
// =============================
async function procesarDataset() {
  if (!currentFile) {
    alert("Primero perfila un archivo.");
    return;
  }

  const approvedRoles = getApprovedRoles();

  const formData = new FormData();
  formData.append("file", currentFile);
  formData.append("separator", normalizeSeparator(separatorInput.value));
  formData.append("encoding", encodingInput.value);
  formData.append("null_threshold", Number(nullThresholdInput.value));
  formData.append("remove_high_null_cols", String(removeHighNullColsInput.checked));
  formData.append("skip_null_removal", String(skipNullRemovalInput.checked));
  formData.append("null_strategy", nullStrategyInput.value);
  formData.append("audience", audienceInput.value);
  formData.append("approved_roles_json", JSON.stringify(approvedRoles));

  try {
    const res = await fetch(`${API_URL}/api/process`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || "No se pudo procesar el dataset.");
    }

    currentRecommendations = (data.recommendations || []).map((rec, index) => ({
      id: index,
      ...rec,
      selected: false,
      parsedColumns: extractColumnsFromRecommendation(rec.columnas),
      normalizedChartType: normalizeChartType(rec.tipo_grafico),
      noSeleccionable: normalizeChartType(rec.tipo_grafico) === "No Graficar Directamente"
    }));

    allRecommendationColumns = buildRecommendationColumnList(currentRecommendations);
    allChartTypes = buildChartTypeList(currentRecommendations);
    includeColumnFilter = [];
    chartTypeFilter = [];

    summaryDiv.innerHTML = `
      <p><strong>Filas procesadas:</strong> ${data.rows_processed}</p>
      <p><strong>Columnas procesadas:</strong> ${data.columns_processed}</p>
    `;

    renderFilterOptions();
    updateFilterButtonLabels();
    renderRecommendations(getFilteredRecommendations());
  } catch (error) {
    console.error(error);
    alert(`Error al procesar el dataset: ${error.message}`);
  }
}

// =============================
// DASHBOARD
// =============================
async function generarDashboard() {
  const selectedCharts = getSelectedRecommendations();

  if (selectedCharts.length === 0) {
    alert("Selecciona al menos un gráfico para el dashboard.");
    return;
  }

  try {
    dashboardBtn.disabled = true;
    dashboardBtn.textContent = "Generando dashboard...";

    const payload = {
      recommendations: selectedCharts.map((item) => ({
        id: item.id,
        tipo_grafico: item.tipo_grafico,
        tipo_canonico: item.normalizedChartType,
        columnas: item.columnas,
        columnas_lista: item.parsedColumns,
        justificacion: item.justificacion,
        es_grafico: !item.noSeleccionable
      }))
    };

    const res = await fetch(`${API_URL}/api/dashboard`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      let errorMessage = "No se pudo generar el dashboard.";
      try {
        const errorData = await res.json();
        errorMessage = errorData.detail || errorData.error || errorMessage;
      } catch (_) {}
      throw new Error(errorMessage);
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "dashboard_agente.pbit";
    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error(error);
    alert(`Error al generar el dashboard: ${error.message}`);
  } finally {
    dashboardBtn.disabled = false;
    dashboardBtn.textContent = "Generar dashboard";
  }
}

// =============================
// REPORTE PDF
// =============================
async function generarReporte() {
  const selectedCharts = getSelectedRecommendations();

  if (selectedCharts.length === 0) {
    alert("Selecciona al menos un gráfico para el reporte.");
    return;
  }

  try {
    reportBtn.disabled = true;
    reportBtn.textContent = "Generando reporte...";

    const payload = {
      graficos: selectedCharts.map((item) => ({
        tipo_grafico: item.tipo_grafico,
        columnas: item.columnas,
        justificacion: item.justificacion
      }))
    };

    const res = await fetch(`${API_URL}/api/report`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      let errorMessage = "No se pudo generar el reporte.";
      try {
        const errorData = await res.json();
        errorMessage = errorData.detail || errorData.error || errorMessage;
      } catch (_) {}
      throw new Error(errorMessage);
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "reporte_visualizaciones.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error(error);
    alert(`Error al generar el reporte: ${error.message}`);
  } finally {
    reportBtn.disabled = false;
    reportBtn.textContent = "Generar reporte";
  }
}

// =============================
// TABLA DE PERFIL
// =============================
function renderProfileTable(profile) {
  if (!profile || profile.length === 0) {
    profileContainer.innerHTML = "<p>No hay columnas para mostrar.</p>";
    return;
  }

  const roleOptions = [
    "identificador",
    "temporal",
    "categórica",
    "discreta",
    "continua",
    "texto libre"
  ];

  let html = `
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Columna</th>
            <th>Tipo original</th>
            <th>Nulos %</th>
            <th>Únicos</th>
            <th>Muestra</th>
            <th>Rol sugerido</th>
            <th>Rol aprobado</th>
          </tr>
        </thead>
        <tbody>
  `;

  profile.forEach((item, index) => {
    const optionsHtml = roleOptions.map(role => {
      const selected = role === item.rol_sugerido ? "selected" : "";
      return `<option value="${escapeHtml(role)}" ${selected}>${escapeHtml(role)}</option>`;
    }).join("");

    html += `
      <tr>
        <td>${escapeHtml(item.columna)}</td>
        <td>${escapeHtml(item.dtype_original)}</td>
        <td>${item.nulos_porcentaje}</td>
        <td>${item.unicos}</td>
        <td>${escapeHtml((item.muestra || []).join(", "))}</td>
        <td><span class="badge">${escapeHtml(item.rol_sugerido)}</span></td>
        <td>
          <select class="role-select" data-index="${index}">
            ${optionsHtml}
          </select>
        </td>
      </tr>
    `;
  });

  html += `
        </tbody>
      </table>
    </div>
  `;

  profileContainer.innerHTML = html;
}

// =============================
// RECOMENDACIONES
// =============================
function renderRecommendations(recommendations) {
  if (!recommendations || recommendations.length === 0) {
    recommendationsDiv.innerHTML = `<p class="empty-state">No hay recomendaciones que cumplan con los filtros.</p>`;
    return;
  }

  let html = "";

  recommendations.forEach((rec) => {
    const selectedClass = rec.selected ? "selected" : "";
    const disabled = rec.noSeleccionable ? "disabled" : "";
    const helperText = rec.noSeleccionable
      ? `<p class="recommendation-disabled-note">Esta recomendación no se puede seleccionar para reporte o dashboard.</p>`
      : "";

    html += `
      <div class="recommendation-card ${selectedClass}" data-rec-id="${rec.id}">
        <div class="recommendation-top">
          <h3 class="recommendation-title">${escapeHtml(rec.tipo_grafico)}</h3>
          <label class="recommendation-picker">
            <input type="checkbox" data-rec-checkbox-id="${rec.id}" ${rec.selected ? "checked" : ""} ${disabled}>
            Elegir
          </label>
        </div>

        <p class="recommendation-columns">Columnas: ${escapeHtml(formatColumns(rec.columnas))}</p>
        <p>${escapeHtml(fixText(rec.justificacion))}</p>
        ${helperText}
      </div>
    `;
  });

  recommendationsDiv.innerHTML = html;
  bindRecommendationCheckboxes();
}

function bindRecommendationCheckboxes() {
  const checkboxes = document.querySelectorAll("[data-rec-checkbox-id]");

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const recId = Number(event.target.getAttribute("data-rec-checkbox-id"));
      const checked = event.target.checked;

      const rec = currentRecommendations.find(item => item.id === recId);
      if (rec) {
        rec.selected = checked;
      }

      const card = document.querySelector(`[data-rec-id="${recId}"]`);
      if (card) {
        if (checked) {
          card.classList.add("selected");
        } else {
          card.classList.remove("selected");
        }
      }
    });
  });
}

function getSelectedRecommendations() {
  return currentRecommendations.filter(item => item.selected && !item.noSeleccionable);
}

// =============================
// FILTROS
// =============================
function togglePanel(openPanel, closePanel) {
  closePanel.classList.add("hidden");
  openPanel.classList.toggle("hidden");
}

function renderFilterOptions() {
  renderSingleFilterOptions("include");
  renderSingleFilterOptions("chartType");
}

function renderSingleFilterOptions(type) {
  const config = getFilterConfig(type);
  const searchTerm = (config.searchInput.value || "").trim().toLowerCase();

  const filteredValues = config.sourceValues.filter(value =>
    value.toLowerCase().includes(searchTerm)
  );

  if (filteredValues.length === 0) {
    config.optionsContainer.innerHTML = `<p class="empty-state">No hay opciones.</p>`;
    return;
  }

  config.optionsContainer.innerHTML = filteredValues.map(value => `
    <label class="excel-option">
      <input
        type="checkbox"
        data-filter-type="${type}"
        value="${escapeHtml(value)}"
        ${config.selectedValues.includes(value) ? "checked" : ""}
      >
      <span>${escapeHtml(value)}</span>
    </label>
  `).join("");

  const checkboxes = config.optionsContainer.querySelectorAll(`input[data-filter-type="${type}"]`);
  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const value = event.target.value;

      if (type === "include") {
        includeColumnFilter = toggleSelectedValue(includeColumnFilter, value, event.target.checked);
      } else if (type === "chartType") {
        chartTypeFilter = toggleSelectedValue(chartTypeFilter, value, event.target.checked);
      }

      updateFilterButtonLabels();
      renderRecommendations(getFilteredRecommendations());
    });
  });
}

function getFilterConfig(type) {
  if (type === "include") {
    return {
      searchInput: includeFilterSearch,
      optionsContainer: includeFilterOptions,
      selectedValues: includeColumnFilter,
      sourceValues: allRecommendationColumns
    };
  }

  return {
    searchInput: chartTypeFilterSearch,
    optionsContainer: chartTypeFilterOptions,
    selectedValues: chartTypeFilter,
    sourceValues: allChartTypes
  };
}

function toggleSelectedValue(list, value, checked) {
  const set = new Set(list);
  if (checked) {
    set.add(value);
  } else {
    set.delete(value);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, "es"));
}

function updateFilterButtonLabels() {
  includeFilterBtn.textContent =
    includeColumnFilter.length === 0
      ? "Seleccionar columnas"
      : `${includeColumnFilter.length} seleccionada(s)`;

  chartTypeFilterBtn.textContent =
    chartTypeFilter.length === 0
      ? "Seleccionar tipos"
      : `${chartTypeFilter.length} seleccionado(s)`;
}

function getFilteredRecommendations() {
  return currentRecommendations.filter((rec) => {
    const cols = rec.parsedColumns || [];
    const chartType = rec.normalizedChartType || normalizeChartType(rec.tipo_grafico);

    const matchesInclude =
      includeColumnFilter.length === 0 ||
      includeColumnFilter.some(col => cols.includes(col));

    const matchesChartType =
      chartTypeFilter.length === 0 ||
      chartTypeFilter.includes(chartType);

    return matchesInclude && matchesChartType;
  });
}

// =============================
// HELPERS
// =============================
function getApprovedRoles() {
  const selects = document.querySelectorAll(".role-select");
  const approvedRoles = {};

  selects.forEach((select) => {
    const index = select.getAttribute("data-index");
    const col = currentProfile[index].columna;
    approvedRoles[col] = select.value;
  });

  return approvedRoles;
}

function extractColumnsFromRecommendation(value) {
  const text = fixText(String(value)).trim();

  if (!text) return [];

  if (text.startsWith("par(") && text.endsWith(")")) {
    const inside = text.slice(4, -1);
    return inside
      .split(",")
      .map(item => item.trim())
      .filter(Boolean);
  }

  return [text];
}

function buildRecommendationColumnList(recommendations) {
  const cols = new Set();

  recommendations.forEach((rec) => {
    (rec.parsedColumns || []).forEach(col => cols.add(col));
  });

  return Array.from(cols).sort((a, b) => a.localeCompare(b, "es"));
}

function buildChartTypeList(recommendations) {
  const types = new Set();

  recommendations.forEach((rec) => {
    if (rec.tipo_grafico) {
      types.add(normalizeChartType(rec.tipo_grafico));
    }
  });

  return Array.from(types).sort((a, b) => a.localeCompare(b, "es"));
}

function normalizeChartType(value) {
  return fixText(String(value)).trim();
}

function formatColumns(value) {
  return fixText(String(value));
}

function normalizeSeparator(value) {
  if (value === "TAB") return "\t";
  return value;
}

function fixText(text) {
  if (typeof text !== "string") return String(text);

  try {
    return decodeURIComponent(escape(text));
  } catch (_) {
    return text;
  }
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}