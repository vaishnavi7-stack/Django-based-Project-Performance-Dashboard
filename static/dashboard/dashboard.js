const charts = {};
let dashboardData = null;
let currentProject = "__all__";
let currentAttentionRows = [];
let currentDelayTeam = "All";
let currentIssueRows = [];
let currentIssueCriticality = "All";
const palette = {
  plan: "#a7b9d6",
  actual: "#9fbe8f",
  warn: "#e6bf91",
  bad: "#f4a6a3",
  neutral: "#9aa8a3",
  soft: "#edf5f2",
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const formatCr = (value) =>
  `${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 })} Cr`;

const formatPct = (value) =>
  `${(Number(value || 0) * 100).toLocaleString("en-IN", { maximumFractionDigits: 1 })}%`;

const formatDeltaPct = (value) => {
  const sign = Number(value || 0) > 0 ? "+" : "";
  return `${sign}${formatPct(value)}`;
};

const formatPp = (value) => {
  const number = Number(value || 0);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toLocaleString("en-IN", { maximumFractionDigits: 1 })} pp`;
};

const formatDays = (value) =>
  `${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 })} days`;

const formatRiskScore = (value) =>
  Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 });

const clampPercent = (value) => Math.max(0, Math.min(100, Number(value || 0)));

const truncateText = (value, maxLength = 118) => {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 3).trim()}...` : text;
};

const formatByType = (value, type) => {
  if (type === "currency_delta") {
    const sign = Number(value || 0) > 0 ? "+" : "";
    return `${sign}${formatCr(value)}`;
  }
  if (type === "currency") return formatCr(value);
  if (type === "percent") return formatPct(value);
  if (type === "percent_delta") return formatDeltaPct(value);
  if (type === "percentage_point") {
    const number = Number(value || 0) * 100;
    const sign = number > 0 ? "+" : "";
    return `${sign}${number.toLocaleString("en-IN", { maximumFractionDigits: 1 })} pp`;
  }
  return Number(value || 0).toLocaleString("en-IN");
};

const trend = (value, label, goodWhenPositive = true) => {
  const number = Number(value || 0);
  const direction = number >= 0 ? "up" : "down";
  const good = goodWhenPositive ? number >= 0 : number <= 0;
  const arrow = number >= 0 ? "↑" : "↓";
  return {
    text: `${arrow} ${Math.abs(number * 100).toLocaleString("en-IN", { maximumFractionDigits: 1 })}% ${label}`,
    className: good ? "good" : "bad",
    direction,
  };
};

const ratioTrend = (value, base, label, goodWhenPositive = true) =>
  trend(base ? Number(value || 0) / Number(base || 1) - 1 : 0, label, goodWhenPositive);

function tableToRows(table) {
  return [...table.querySelectorAll("tr")].map((row) =>
    [...row.children].map((cell) => cell.textContent.trim().replace(/\s+/g, " ")),
  );
}

function activeExportRows() {
  const activePanel = document.querySelector(".report-page.active");
  if (activePanel?.dataset.pagePanel === "tables") {
    const dataTable = activePanel.querySelector(".data-table-panel.active table");
    if (dataTable) return tableToRows(dataTable);
  }
  const table = activePanel?.querySelector("table");
  if (table) return tableToRows(table);
  return [
    ["Metric", "Value", "Note"],
    ...[...document.querySelectorAll(".kpi")].map((card) => [
      card.querySelector(".label")?.textContent.trim() || "",
      card.querySelector(".value")?.textContent.trim() || "",
      card.querySelector(".note")?.textContent.trim() || "",
    ]),
    [],
    ["Variance", "Value", "Note"],
    ...[...document.querySelectorAll(".variance-card")].map((card) => [
      card.querySelector(".label")?.textContent.trim() || "",
      card.querySelector("strong")?.textContent.trim() || "",
      card.querySelector(".note")?.textContent.trim() || "",
    ]),
  ];
}

function downloadBlob(filename, mimeType, content) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function currentPageName() {
  return document.querySelector(".nav-item.active")?.textContent.trim().replace(/\s+/g, "-").toLowerCase() || "dashboard";
}

function exportCsv() {
  const csv = activeExportRows()
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  downloadBlob(`${currentPageName()}.csv`, "text/csv;charset=utf-8", csv);
}

function exportExcel() {
  const rows = activeExportRows()
    .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
    .join("");
  const html = `<html><body><table>${rows}</table></body></html>`;
  downloadBlob(`${currentPageName()}.xls`, "application/vnd.ms-excel;charset=utf-8", html);
}

function exportPdf() {
  window.print();
}

function toggleExportMenu(open) {
  const menu = document.getElementById("exportMenu");
  const button = document.getElementById("exportMenuToggle");
  if (!menu || !button) return;
  const nextOpen = open ?? !menu.classList.contains("open");
  menu.classList.toggle("open", nextOpen);
  button.setAttribute("aria-expanded", nextOpen ? "true" : "false");
}

function applyTheme(theme) {
  document.body.classList.toggle("dark", theme === "dark");
  localStorage.setItem("dashboard-theme", theme);
  document.getElementById("themeToggle").textContent = theme === "dark" ? "Light mode" : "Dark mode";
  if (dashboardData) renderDashboard(dashboardData, currentProject);
}

function applySidebarState(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem("dashboard-sidebar-collapsed", collapsed ? "true" : "false");
  const sidebarButton = document.getElementById("sidebarToggle");
  const restoreButton = document.getElementById("sidebarRestore");
  if (sidebarButton) {
    sidebarButton.textContent = "Hide";
    sidebarButton.setAttribute("aria-label", "Hide sidebar");
  }
  if (restoreButton) restoreButton.hidden = !collapsed;
  setTimeout(() => Object.values(charts).forEach((chart) => chart.resize()), 80);
}

function destroyChart(id) {
  if (charts[id]) {
    charts[id].destroy();
  }
}

function makeChart(id, config) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  destroyChart(id);
  charts[id] = new Chart(canvas, config);
}

function renderKpis(kpis) {
  const grid = document.getElementById("kpiGrid");
  const rows = filteredAiRows(dashboardData?.ai, currentProject);
  const atRisk = rows.filter((row) => row.risk_status !== "Normal").length;
  const items = [
    ["Total Projects", kpis.project_count, "Projects in the current selection"],
    ["Total Contract Value", formatCr(kpis.contract_value || kpis.order_book), "Portfolio contract value"],
    ["Billing Achievement", formatPct(kpis.billing_achievement), "Actual billing against planned billing"],
    ["Average Progress", formatPct(kpis.avg_actual_progress), "Average actual progress across overall rows"],
    ["At-Risk Projects", atRisk, "AI high and medium risk projects"],
    ["Budget Overruns", kpis.budget_overrun_projects, "Projects where current budget exceeds contract value"],
    ["Open Critical Issues", kpis.open_issues, "Open items in the critical issue register"],
    ["Avg Procurement Delay", formatDays(kpis.avg_procurement_delay), "Average delay days in procurement actions"],
  ];

  grid.innerHTML = items
    .map(
      ([label, value, note]) => `
        <article class="kpi context-card">
          <div class="label">${escapeHtml(label)}</div>
          <div class="value">${escapeHtml(value)}</div>
          <div class="note">${escapeHtml(note)}</div>
        </article>
      `,
    )
    .join("");
}

function renderVarianceCards(cards) {
  const grid = document.getElementById("varianceCards");
  grid.innerHTML = cards
    .map(
      (card) => `
        <article class="variance-card executive-card ${card.status}">
          <div>
            <div class="label">${escapeHtml(card.label)}</div>
            <div class="note">${escapeHtml(card.note)}</div>
          </div>
          <span class="status-chip ${card.status}">${card.status === "good" ? "Favorable" : "Needs attention"}</span>
          <strong>${escapeHtml(formatByType(card.value, card.format))}</strong>
        </article>
      `,
    )
    .join("");
}

function renderBilling(data) {
  makeChart("billingTrend", {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        {
          label: "Plan",
          data: data.plan,
          borderColor: palette.plan,
          backgroundColor: "rgba(167, 185, 214, 0.24)",
          tension: 0.28,
          fill: true,
        },
        {
          label: "Actual",
          data: data.actual,
          borderColor: palette.actual,
          backgroundColor: "rgba(159, 190, 143, 0.24)",
          tension: 0.28,
          fill: true,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { position: "bottom" } },
      scales: { y: { ticks: { callback: (value) => `${value} Cr` } } },
    },
  });
}

function renderProgress(data) {
  destroyChart("progressBars");
  const stack = document.getElementById("projectProgressBars");
  if (!stack) return;
  if (!data.length) {
    stack.innerHTML = '<div class="empty-state">No project progress rows for this selection.</div>';
    return;
  }
  stack.innerHTML = data
    .map((row) => {
      const parts = [
        ["completed", row.completed, "Completed"],
        ["overdue", row.overdue, "Overdue"],
        ["pending", row.pending, "Pending"],
      ].filter(([, value]) => Number(value || 0) > 0.0005);
      return `
        <div class="project-progress-row">
          <div class="project-progress-label">
            <strong>${escapeHtml(row.project)}${row.revision ? ` — ${escapeHtml(row.revision)}` : ""}</strong>
            <span>Internal Comm: ${escapeHtml(row.internal_comm || "NA")}</span>
            <span>Contract Comm: ${escapeHtml(row.contract_comm || "NA")}</span>
          </div>
          <div class="project-progress-track" aria-label="${escapeHtml(row.project)} progress">
            ${parts
              .map(([className, value, label]) => {
                const pct = Math.round(Number(value || 0) * 100);
                const stylePct = Math.max(Number(value || 0) * 100, pct > 0 && pct < 2 ? 2 : 0);
                return `
                  <div class="progress-segment ${className}" style="width:${stylePct}%;" title="${escapeHtml(label)} ${pct}%">
                    ${pct >= 7 ? `<span>${pct}%</span>` : ""}
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>
      `;
    })
    .join("");
}

function renderIssues(data) {
  makeChart("issuesChart", {
    type: "doughnut",
    data: {
      labels: data.labels,
      datasets: [
        {
          data: data.values,
          backgroundColor: [palette.bad, palette.warn, palette.plan, palette.actual, palette.neutral],
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      onClick: (event, elements, chart) => {
        const activeElement =
          elements[0] || chart.getElementsAtEventForMode(event, "nearest", { intersect: false }, true)[0];
        if (!activeElement) return;
        const criticality = data.labels[activeElement.index];
        activatePage("tables");
        setDataTable("issues");
        setIssueCriticality(criticality);
      },
      onHover: (event, elements) => {
        if (event.native?.target) event.native.target.style.cursor = elements.length ? "pointer" : "default";
      },
      plugins: { legend: { position: "right", labels: { boxWidth: 12, padding: 14 } } },
    },
  });
}

function renderBudget(data) {
  makeChart("budgetChart", {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [
        { label: "Contract value", data: data.contract_value, backgroundColor: palette.plan },
        { label: "Current budget", data: data.current_budget, backgroundColor: palette.warn },
        { label: "Actual billing", data: data.actual_billing, backgroundColor: palette.actual },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: { y: { ticks: { callback: (value) => `${value} Cr` } } },
    },
  });
}

function renderDelays(data) {
  makeChart("delayChart", {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [{ label: "Items", data: data.values, backgroundColor: data.labels.map((label) => {
        if (label.toLowerCase().includes("delayed") || label.toLowerCase().includes("overdue")) return palette.bad;
        if (label.toLowerCase().includes("time")) return palette.actual;
        return palette.plan;
      }) }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
    },
  });
}

function renderHinderance(data) {
  makeChart("hinderanceChart", {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [{ label: "Records", data: data.values, backgroundColor: palette.actual }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { autoSkip: false, maxRotation: 45, minRotation: 35 } },
        y: { beginAtZero: true },
      },
    },
  });
}

function renderRanking(id, rows, config) {
  const list = document.getElementById(id);
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = '<div class="empty-state">No items to show for this selection.</div>';
    return;
  }
  list.innerHTML = rows
    .map((row, index) => {
      const metric = config.metric(row);
      const sub = config.sub ? config.sub(row) : "";
      return `
        <div class="rank-item">
          <span class="rank-number">${index + 1}</span>
          <div>
            <strong>${escapeHtml(row.project)}</strong>
            <small>${escapeHtml(sub)}</small>
          </div>
          <b class="${Number(config.rawMetric ? config.rawMetric(row) : 0) < 0 ? "bad-text" : ""}">${escapeHtml(metric)}</b>
        </div>
      `;
    })
    .join("");
}

function renderRankings(rankings, mfcTopDelays) {
  renderRanking("billingGapRanking", rankings.billing_gap, {
    metric: (row) => formatCr(row.gap),
    rawMetric: (row) => row.gap,
    sub: (row) => `Plan ${formatCr(row.plan)} / Actual ${formatCr(row.actual)}`,
  });
  renderRanking("budgetOverrunRanking", rankings.budget_overrun, {
    metric: (row) => formatCr(row.overrun),
    rawMetric: (row) => row.overrun,
    sub: (row) => `Contract ${formatCr(row.contract)} / Budget ${formatCr(row.budget)}`,
  });
  renderRanking("progressRanking", rankings.lowest_progress, {
    metric: (row) => formatPct(row.actual),
    rawMetric: (row) => row.gap,
    sub: (row) => `Gap ${formatDeltaPct(row.gap)}`,
  });
  renderRanking("delayRanking", mfcTopDelays, {
    metric: (row) => `${row.max_days} days`,
    rawMetric: (row) => row.max_days,
    sub: (row) => `${row.items} delayed items`,
  });
}

function renderCommissioning(items) {
  const list = document.getElementById("commissioningList");
  if (!items.length) {
    list.innerHTML = '<div class="empty-state">No commissioning dates for this selection.</div>';
    return;
  }
  list.innerHTML = items
    .map((item) => {
      const cls = item.days_delta <= 0 ? "good" : "bad";
      const label = item.days_delta <= 0 ? `${Math.abs(item.days_delta)}d early` : `${item.days_delta}d late`;
      return `
        <div class="list-item">
          <div>
            <div class="list-title">${escapeHtml(item.project)}</div>
            <div class="list-subtitle">Internal ${escapeHtml(item.internal_date)} / Contract ${escapeHtml(item.contract_date)}</div>
          </div>
          <span class="pill ${cls}">${escapeHtml(label)}</span>
        </div>
      `;
    })
    .join("");
}

function renderAttention(rows) {
  currentAttentionRows = rows;
  const body = document.getElementById("attentionRows");
  const visibleRows = currentDelayTeam === "All" ? rows : rows.filter((row) => row.team === currentDelayTeam);
  body.innerHTML = visibleRows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.area)}</td>
          <td>${escapeHtml(row.project)}</td>
          <td>${escapeHtml(row.priority || "")}</td>
          <td>${escapeHtml(row.item)}</td>
          <td>${escapeHtml(row.owner || row.status || "")}</td>
          <td>${escapeHtml(row.due || "")}</td>
          <td>${escapeHtml(row.delay_days || "")}</td>
          <td>${escapeHtml(row.aging || "")}</td>
        </tr>
      `,
    )
    .join("");
}

function setDelayTeam(team) {
  currentDelayTeam = team;
  document.querySelectorAll("#delayTeamFilter button").forEach((button) => {
    button.classList.toggle("active", button.dataset.team === team);
  });
  renderAttention(currentAttentionRows);
}

function setDataTable(target) {
  document.querySelectorAll("#dataTableTabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tableTarget === target);
  });
  document.querySelectorAll(".data-table-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tablePanel === target);
  });
}

function renderMfcRows(rows) {
  const body = document.getElementById("mfcRows");
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.project)}</td>
          <td>${escapeHtml(row.item)}</td>
          <td>${escapeHtml(row.po_plan)}</td>
          <td>${escapeHtml(row.po_actual)}</td>
          <td>${escapeHtml(row.mfc_plan)}</td>
          <td>${escapeHtml(row.mfc_actual)}</td>
          <td class="${row.delay_days > 0 ? "bad-text" : ""}">${escapeHtml(row.delay_days)}</td>
          <td>${escapeHtml(row.status)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderIssueFilter(rows) {
  const filter = document.getElementById("issueCriticalityFilter");
  if (!filter) return;
  const values = ["All", ...new Set(rows.map((row) => row.criticality).filter(Boolean))];
  if (!values.includes(currentIssueCriticality)) currentIssueCriticality = "All";
  filter.innerHTML = values
    .map(
      (value) => `
        <button class="${value === currentIssueCriticality ? "active" : ""}" data-criticality="${escapeHtml(value)}" type="button">${escapeHtml(value)}</button>
      `,
    )
    .join("");
  filter.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => setIssueCriticality(button.dataset.criticality));
  });
}

function setIssueCriticality(criticality) {
  currentIssueCriticality = criticality || "All";
  document.querySelectorAll("#issueCriticalityFilter button").forEach((button) => {
    button.classList.toggle("active", button.dataset.criticality === currentIssueCriticality);
  });
  renderIssueRows(currentIssueRows, false);
}

function renderIssueRows(rows, rebuildFilter = true) {
  currentIssueRows = rows;
  const body = document.getElementById("issueRows");
  if (rebuildFilter) renderIssueFilter(rows);
  const visibleRows =
    currentIssueCriticality === "All" ? rows : rows.filter((row) => row.criticality === currentIssueCriticality);
  if (!visibleRows.length) {
    body.innerHTML = '<tr><td colspan="6">No issue rows for this filter.</td></tr>';
    return;
  }
  body.innerHTML = visibleRows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.timestamp)}</td>
          <td>${escapeHtml(row.project)}</td>
          <td>${escapeHtml(row.criticality)}</td>
          <td>${escapeHtml(row.issue)}</td>
          <td>${escapeHtml(row.responsibility)}</td>
          <td>${escapeHtml(row.status)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderBudgetRows(rows) {
  const body = document.getElementById("budgetRows");
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.project)}</td>
          <td>${escapeHtml(formatCr(row.contract_value))}</td>
          <td>${escapeHtml(formatCr(row.initial_budget))}</td>
          <td>${escapeHtml(formatCr(row.current_budget))}</td>
          <td>${row.final_cost === null ? "" : escapeHtml(formatCr(row.final_cost))}</td>
          <td class="${row.budget_variance < 0 ? "bad-text" : ""}">${escapeHtml(formatCr(row.budget_variance))}</td>
          <td>${escapeHtml(formatPct(row.target_pbt))}</td>
          <td>${escapeHtml(formatPct(row.current_pbt))}</td>
          <td class="${row.pbt_gap < 0 ? "bad-text" : ""}">${escapeHtml(formatDeltaPct(row.pbt_gap))}</td>
        </tr>
      `,
    )
    .join("");
}

function renderHinderanceRows(rows) {
  const body = document.getElementById("hinderanceRows");
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.date)}</td>
          <td>${escapeHtml(row.project)}</td>
          <td>${escapeHtml(row.block)}</td>
          <td>${escapeHtml(row.hinderance)}</td>
          <td>${escapeHtml(row.start)}</td>
          <td>${escapeHtml(row.end)}</td>
          <td>${escapeHtml(row.duration)}</td>
          <td>${escapeHtml(row.remarks)}</td>
        </tr>
      `,
    )
    .join("");
}

function driverClass(driver) {
  const text = String(driver || "").toLowerCase();
  if (text.includes("procurement")) return "procurement";
  if (text.includes("design")) return "design";
  if (text.includes("execution")) return "execution";
  if (text.includes("billing")) return "billing";
  if (text.includes("pbt") || text.includes("budget")) return "finance";
  if (text.includes("issue")) return "issue";
  if (text.includes("hindrance")) return "hindrance";
  if (text.includes("progress")) return "progress";
  return "default";
}

function renderDriverTags(drivers, fallback = "") {
  const values = (drivers || []).length
    ? drivers
    : String(fallback || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
  if (!values.length) return '<span class="driver-tag default">No dominant driver</span>';
  return `
    <div class="driver-tags">
      ${values.map((driver) => `<span class="driver-tag ${driverClass(driver)}">${escapeHtml(driver)}</span>`).join("")}
    </div>
  `;
}

function riskStatusClass(status) {
  if (status === "High Risk") return "high";
  if (status === "Medium Risk") return "medium";
  return "normal";
}

function healthStatusClass(status) {
  return String(status || "On Track").toLowerCase().replace(/\s+/g, "-");
}

function filteredAiRows(ai, project) {
  const rows = ai?.risks || [];
  if (project === "__all__") return rows;
  return rows.filter((row) => row.project === project);
}

function aiRowsForCurrentProject(ai, project) {
  return filteredAiRows(ai, project).sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0));
}

function renderAiCards(rows) {
  const grid = document.getElementById("aiKpiGrid");
  if (!grid) return;
  const high = rows.filter((row) => row.risk_status === "High Risk").length;
  const medium = rows.filter((row) => row.risk_status === "Medium Risk").length;
  const normal = rows.filter((row) => row.risk_status === "Normal").length;
  const average = rows.length
    ? rows.reduce((sum, row) => sum + Number(row.risk_score || 0), 0) / rows.length
    : 0;
  const cards = [
    { label: "Projects Analysed", value: rows.length, note: "Project rows in current selection", tone: "neutral" },
    { label: "High Risk Projects", value: high, note: "Immediate review candidates", tone: "high" },
    { label: "Medium Risk Projects", value: medium, note: "Watchlist projects", tone: "medium" },
    { label: "Normal Projects", value: normal, note: "No abnormal risk signal", tone: "normal" },
    {
      label: "Average Risk Index",
      value: formatRiskScore(average),
      note: "0 to 100, higher means riskier",
      tone: "average",
      meter: clampPercent(average),
    },
  ];
  grid.innerHTML = cards
    .map(
      (card) => `
        <article class="ai-kpi ${card.tone}">
          <span>${escapeHtml(card.label)}</span>
          <strong>${escapeHtml(card.value)}</strong>
          ${card.meter !== undefined ? `<div class="risk-meter" aria-hidden="true"><i style="width:${card.meter}%;"></i></div>` : ""}
          <small>${escapeHtml(card.note)}</small>
        </article>
      `,
    )
    .join("");
}

function renderAiTopRisk(rows) {
  const list = document.getElementById("aiTopRiskList");
  if (!list) return;
  const topRows = [...rows].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0)).slice(0, 8);
  if (!topRows.length) {
    list.innerHTML = '<div class="empty-state">No AI risk rows for this selection.</div>';
    return;
  }
  list.innerHTML = topRows
    .map(
      (row) => `
        <div class="rank-item ai-rank-item">
          <span class="rank-number">${escapeHtml(row.rank)}</span>
          <div>
            <strong>${escapeHtml(row.project)}</strong>
            ${renderDriverTags(row.drivers, row.risk_reason)}
            <small class="muted-reason">${escapeHtml(row.risk_reason)}</small>
          </div>
          <div class="ai-rank-metric">
            <span class="risk-status ${riskStatusClass(row.risk_status)}">${escapeHtml(row.risk_status)}</span>
            <b>${escapeHtml(formatRiskScore(row.risk_score))}</b>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderRiskDistribution(ai, project) {
  const rows = filteredAiRows(ai, project);
  const labels = ["Critical", "At Risk", "Watch", "On Track"];
  const values = labels.map((label) => rows.filter((row) => row.health_status === label).length);
  makeChart("riskDistributionChart", {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: [palette.bad, "#e6bf91", palette.plan, palette.actual],
          borderWidth: 0,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function renderAiDrivers(ai, rows, project) {
  const list = document.getElementById("aiDriverList");
  if (!list) return;
  let drivers = ai?.driver_counts || [];
  if (project !== "__all__") {
    const counts = rows.flatMap((row) => row.drivers || []).reduce((acc, driver) => {
      acc[driver] = (acc[driver] || 0) + 1;
      return acc;
    }, {});
    drivers = Object.entries(counts).map(([driver, projects]) => ({ driver, projects }));
  }
  if (!drivers.length) {
    list.innerHTML = '<div class="empty-state">No dominant risk drivers for this selection.</div>';
    return;
  }
  list.innerHTML = drivers
    .slice(0, 8)
    .map(
      (driver) => `
        <div class="driver-item">
          <span>${escapeHtml(driver.driver)}</span>
          <strong>${escapeHtml(driver.projects)} project${Number(driver.projects) === 1 ? "" : "s"}</strong>
        </div>
      `,
    )
    .join("");
}

function renderActionList(id, rows) {
  const list = document.getElementById(id);
  if (!list) return;
  const topRows = [...rows].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0)).slice(0, 5);
  if (!topRows.length) {
    list.innerHTML = '<div class="empty-state">No actions for this selection.</div>';
    return;
  }
  list.innerHTML = topRows
    .map(
      (row) => `
        <div class="action-item">
          <div>
            <strong>${escapeHtml(row.project)}</strong>
            <small>Risk index ${escapeHtml(formatRiskScore(row.risk_score))}</small>
          </div>
          ${renderDriverTags(row.drivers, row.risk_reason)}
          <p title="${escapeHtml(row.recommended_action)}">${escapeHtml(truncateText(row.recommended_action))}</p>
          <span class="health-badge ${healthStatusClass(row.health_status)}">${escapeHtml(row.health_status)}</span>
        </div>
      `,
    )
    .join("");
}

function renderAiInsight(ai, rows, project) {
  const box = document.getElementById("aiInsightBox");
  if (!box) return;
  if (project !== "__all__") {
    if (!rows.length) {
      box.textContent = "No AI risk record is available for this project.";
      return;
    }
    const row = rows[0];
    box.textContent = `${row.project} is ${row.risk_status.toLowerCase()} with a ${row.priority.toLowerCase()} priority. Main reason: ${row.risk_reason}.`;
    return;
  }
  box.textContent = ai?.insight || "AI risk insight is not available.";
}

function renderAiRiskRows(rows) {
  const body = document.getElementById("aiRiskRows");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="13">No AI risk rows for this selection.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.rank)}</td>
          <td>${escapeHtml(row.project)}</td>
          <td><span class="health-badge ${healthStatusClass(row.health_status)}">${escapeHtml(row.health_status)}</span></td>
          <td><span class="risk-status ${riskStatusClass(row.risk_status)}">${escapeHtml(row.risk_status)}</span></td>
          <td>${escapeHtml(row.priority)}</td>
          <td><strong>${escapeHtml(formatRiskScore(row.risk_score))}</strong></td>
          <td>${escapeHtml(row.risk_reason)}</td>
          <td>${escapeHtml(row.recommended_action)}</td>
          <td class="${row.progress_difference < 0 ? "bad-text" : ""}">${escapeHtml(formatPp(row.progress_difference))}</td>
          <td>${escapeHtml(row.issue_count)}</td>
          <td>${escapeHtml(formatDays(row.avg_procurement_delay))}</td>
          <td>${row.billing_achievement === null ? "NA" : escapeHtml(formatPct(row.billing_achievement))}</td>
          <td class="${row.current_pbt < 0 ? "bad-text" : ""}">${escapeHtml(formatPct(row.current_pbt))}</td>
        </tr>
      `,
    )
    .join("");
}

function renderAI(ai, project) {
  const rows = aiRowsForCurrentProject(ai, project);
  const modelPill = document.getElementById("aiModelPill");
  if (modelPill) {
    modelPill.textContent = `${ai?.model || "AI model"} | ${(ai?.features_used || []).length} risk signals`;
  }
  renderAiCards(rows);
  renderAiTopRisk(rows);
  renderRiskDistribution(ai, project);
  renderAiDrivers(ai, rows, project);
  renderAiInsight(ai, rows, project);
  renderActionList("overviewActionList", rows);
  renderActionList("aiActionList", rows);
  renderAiRiskRows(rows);
}

function renderDelayAreaCards(rows) {
  const grid = document.getElementById("delayAreaCards");
  if (!grid) return;
  const teams = ["Design", "Procurement", "Construction"];
  grid.innerHTML = teams
    .map((team) => {
      const teamRows = rows.filter((row) => row.team === team);
      const maxDelay = teamRows.reduce((max, row) => Math.max(max, Number(row.delay_days || 0)), 0);
      const aged = teamRows.filter((row) => Number(row.delay_days || 0) >= 60).length;
      const severity = maxDelay >= 180 || aged >= 10 ? "critical" : maxDelay >= 30 || aged > 0 ? "warning" : "stable";
      return `
        <button class="delay-area-card ${severity}" data-team="${escapeHtml(team)}" type="button">
          <span>${escapeHtml(team)}</span>
          <strong>${teamRows.length}</strong>
          <small>${escapeHtml(formatDays(maxDelay))} max delay</small>
          <b>${aged} aged 60+ days</b>
        </button>
      `;
    })
    .join("");
  grid.querySelectorAll(".delay-area-card").forEach((card) => {
    card.addEventListener("click", () => {
      activatePage("tables");
      setDataTable("delays");
      setDelayTeam(card.dataset.team);
    });
  });
}

function populateProjects(projects) {
  const select = document.getElementById("projectFilter");
  select.insertAdjacentHTML(
    "beforeend",
    projects.map((project) => `<option value="${escapeHtml(project)}">${escapeHtml(project)}</option>`).join(""),
  );
}

function renderDashboard(data, project = "__all__") {
  dashboardData = data;
  currentProject = project;
  const view = project === "__all__" ? data.portfolio : data.projects[project];
  document.getElementById("refreshMeta").textContent = `Last refresh: ${data.summary.last_updated}`;
  document.getElementById("sourceNote").textContent =
    `Source: ${data.summary.source_file} | Generated: ${data.summary.last_updated} | Projects: ${data.summary.project_count}`;
  renderKpis(view.kpis);
  renderVarianceCards(view.variance_cards);
  renderAI(data.ai, project);
  renderBilling(view.billing_trend);
  renderProgress(view.project_progress_bars);
  renderIssues(view.issues);
  renderBudget(view.budget);
  renderDelays(view.delays);
  renderHinderance(view.hinderance);
  renderRankings(view.rankings, view.mfc_top_delays);
  renderCommissioning(view.commissioning);
  renderAttention(view.attention);
  renderDelayAreaCards(view.attention);
  renderMfcRows(view.mfc_details);
  renderIssueRows(view.critical_issue_details);
  renderBudgetRows(view.budget_details);
  renderHinderanceRows(view.hinderance_details);
  Object.values(charts).forEach((chart) => chart.resize());
}

function activatePage(page) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === page);
  });
  document.querySelectorAll(".report-page").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.pagePanel === page);
  });
  setTimeout(() => Object.values(charts).forEach((chart) => chart.resize()), 60);
}

fetch("/api/dashboard/")
  .then((response) => response.json())
  .then((data) => {
    document.body.classList.remove("loading");
    populateProjects(data.project_names);
    renderDashboard(data);
    document.getElementById("projectFilter").addEventListener("change", (event) => {
      renderDashboard(data, event.target.value);
    });
    document.querySelectorAll(".nav-item").forEach((button) => {
      button.addEventListener("click", () => activatePage(button.dataset.page));
    });
    document.querySelectorAll("#delayTeamFilter button").forEach((button) => {
      button.addEventListener("click", () => setDelayTeam(button.dataset.team));
    });
    document.querySelectorAll("#dataTableTabs button").forEach((button) => {
      button.addEventListener("click", () => setDataTable(button.dataset.tableTarget));
    });
    document.getElementById("themeToggle").addEventListener("click", () => {
      applyTheme(document.body.classList.contains("dark") ? "light" : "dark");
    });
    document.getElementById("sidebarToggle").addEventListener("click", () => {
      applySidebarState(!document.body.classList.contains("sidebar-collapsed"));
    });
    document.getElementById("sidebarRestore").addEventListener("click", () => {
      applySidebarState(false);
    });
    document.getElementById("exportMenuToggle").addEventListener("click", (event) => {
      event.stopPropagation();
      toggleExportMenu();
    });
    document.getElementById("exportCsv").addEventListener("click", () => {
      exportCsv();
      toggleExportMenu(false);
    });
    document.getElementById("exportExcel").addEventListener("click", () => {
      exportExcel();
      toggleExportMenu(false);
    });
    document.getElementById("exportPdf").addEventListener("click", () => {
      exportPdf();
      toggleExportMenu(false);
    });
    document.addEventListener("click", (event) => {
      if (!document.getElementById("exportMenu")?.contains(event.target)) toggleExportMenu(false);
    });
  });

applyTheme(localStorage.getItem("dashboard-theme") || "light");
applySidebarState(localStorage.getItem("dashboard-sidebar-collapsed") === "true");
