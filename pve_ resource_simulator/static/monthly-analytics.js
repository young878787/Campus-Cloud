const analyticsState = {
  payload: null,
  filter: "",
};

const analyticsElements = {
  title: document.querySelector("#analytics-title"),
  generated: document.querySelector("#analytics-generated"),
  timezone: document.querySelector("#analytics-timezone"),
  error: document.querySelector("#analytics-error"),
  loading: document.querySelector("#analytics-loading"),
  content: document.querySelector("#analytics-content"),
  refresh: document.querySelector("#refresh-analytics"),
  clusterMetrics: document.querySelector("#cluster-metrics"),
  clusterHourlyGrid: document.querySelector("#cluster-hourly-grid"),
  nodeCardGrid: document.querySelector("#node-card-grid"),
  guestTableBody: document.querySelector("#guest-table-body"),
  guestFilter: document.querySelector("#guest-filter"),
};

analyticsElements.refresh?.addEventListener("click", () => {
  void loadAnalytics();
});

analyticsElements.guestFilter?.addEventListener("input", (event) => {
  analyticsState.filter = String(event.target.value || "").trim().toLowerCase();
  renderGuestTable();
});

void loadAnalytics();

async function loadAnalytics() {
  setLoading(true);
  clearError();

  try {
    const response = await fetch("/api/v1/proxmox/monthly-analytics");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to load analytics.");
    }

    analyticsState.payload = payload;
    renderAnalytics();
  } catch (error) {
    showError(error.message || "Failed to load analytics.");
  } finally {
    setLoading(false);
  }
}

function renderAnalytics() {
  const payload = analyticsState.payload;
  if (!payload) return;

  if (analyticsElements.title) {
    analyticsElements.title.textContent = `${payload.host} · ${payload.month_label} usage analytics`;
  }
  if (analyticsElements.generated) {
    analyticsElements.generated.textContent = `Generated: ${formatDateTime(payload.generated_at)}`;
  }
  if (analyticsElements.timezone) {
    analyticsElements.timezone.textContent = `Timezone: ${payload.timezone}`;
  }

  renderClusterMetrics();
  renderClusterHourly();
  renderNodeCards();
  renderGuestTable();
}

function renderClusterMetrics() {
  const cluster = analyticsState.payload?.cluster;
  if (!cluster || !analyticsElements.clusterMetrics) return;

  analyticsElements.clusterMetrics.innerHTML = [
    metricCard("Nodes", `${cluster.node_count}`),
    metricCard("Guests", `${cluster.guest_count}`),
    metricCard("Current CPU", formatPercent(cluster.current_cpu_ratio)),
    metricCard("Current RAM", formatPercent(cluster.current_memory_ratio)),
    metricCard("Current Disk", formatPercent(cluster.current_disk_ratio)),
    metricCard("Baseline CPU", formatPercent(cluster.average_cpu_ratio)),
    metricCard("Baseline RAM", formatPercent(cluster.average_memory_ratio)),
    metricCard("Baseline Disk", formatPercent(cluster.average_disk_ratio)),
    metricCard("Peak CPU", formatPercent(cluster.peak_cpu_ratio)),
    metricCard("Peak RAM", formatPercent(cluster.peak_memory_ratio)),
    metricCard("Peak Disk", formatPercent(cluster.peak_disk_ratio)),
  ].join("");
}

function renderClusterHourly() {
  const hourly = analyticsState.payload?.cluster?.hourly || [];
  if (!analyticsElements.clusterHourlyGrid) return;

  analyticsElements.clusterHourlyGrid.innerHTML = hourly
    .map(
      (item) => `
        <article class="hourly-card">
          <p class="hourly-label">${escapeHtml(item.label)}</p>
          <p class="hourly-value">CPU ${formatPercent(item.cpu_ratio)}</p>
          <p class="hourly-value">RAM ${formatPercent(item.memory_ratio)}</p>
          <p class="hourly-value">Disk ${formatPercent(item.disk_ratio)}</p>
          <p class="hourly-meta">Samples ${item.sample_count || 0}${item.loadavg_1 != null ? ` · Load ${item.loadavg_1.toFixed(2)}` : ""}</p>
        </article>
      `,
    )
    .join("");
}

function renderNodeCards() {
  const nodes = analyticsState.payload?.nodes || [];
  if (!analyticsElements.nodeCardGrid) return;

  analyticsElements.nodeCardGrid.innerHTML = nodes
    .map(
      (node) => `
        <article class="node-card">
          <div class="node-card-head">
            <div>
              <p class="section-kicker">Node</p>
              <h3>${escapeHtml(node.name)}</h3>
            </div>
            <p class="node-status ${node.status === "online" ? "online" : ""}">${escapeHtml(node.status || "unknown")}</p>
          </div>
          <div class="node-metrics">
            <p>Current CPU <strong>${formatPercent(node.current_cpu_ratio)}</strong></p>
            <p>Current RAM <strong>${formatPercent(node.current_memory_ratio)}</strong></p>
            <p>Current Disk <strong>${formatPercent(node.current_disk_ratio)}</strong></p>
            <p>Baseline CPU <strong>${formatPercent(node.average_cpu_ratio)}</strong></p>
            <p>Baseline RAM <strong>${formatPercent(node.average_memory_ratio)}</strong></p>
            <p>Baseline Disk <strong>${formatPercent(node.average_disk_ratio)}</strong></p>
            <p>Peak CPU <strong>${formatPercent(node.peak_cpu_ratio)}</strong></p>
            <p>Loadavg <strong>${formatLoadavg(node.current_loadavg)}</strong></p>
            ${node.fetch_error ? `<p class="fetch-warning">${escapeHtml(node.fetch_error)}</p>` : ""}
          </div>
          <div class="mini-hourly-row">
            ${renderMiniBars(node.hourly || [], "cpu_ratio")}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderGuestTable() {
  const guestTypes = analyticsState.payload?.guest_types || [];
  if (!analyticsElements.guestTableBody) return;

  const filtered = guestTypes.filter((group) => {
    if (!analyticsState.filter) return true;
    const haystack = `${group.type_label} ${(group.sample_names || []).join(" ")}`.toLowerCase();
    return haystack.includes(analyticsState.filter);
  });

  if (!filtered.length) {
    analyticsElements.guestTableBody.innerHTML = `
      <tr>
        <td colspan="6" class="guest-empty">No guest types match the current filter.</td>
      </tr>
    `;
    return;
  }

  analyticsElements.guestTableBody.innerHTML = filtered
    .map(
      (group) => `
        <tr>
          <td>
            <div class="guest-main">
              <strong>${escapeHtml(group.type_label)}</strong>
              <span>${escapeHtml(formatGroupConfig(group))}</span>
            </div>
          </td>
          <td>${group.guest_count}</td>
          <td>${formatTriple(group.current_cpu_ratio, group.current_memory_ratio, group.current_disk_ratio)}</td>
          <td>${formatTriple(group.average_cpu_ratio, group.average_memory_ratio, group.average_disk_ratio)}</td>
          <td>${formatTriple(group.peak_cpu_ratio, group.peak_memory_ratio, group.peak_disk_ratio)}</td>
          <td>${escapeHtml((group.sample_names || []).join(", ") || "n/a")}</td>
        </tr>
      `,
    )
    .join("");
}

function metricCard(label, value) {
  return `
    <article class="metric-card">
      <p class="metric-label">${escapeHtml(label)}</p>
      <p class="metric-value">${escapeHtml(value)}</p>
    </article>
  `;
}

function renderMiniBars(points, key) {
  return points
    .map((point) => {
      const value = Number(point?.[key] || 0);
      const height = Math.max(8, Math.round(value * 100));
      return `<span class="mini-bar" style="height:${height}%;" title="${escapeHtml(`${point.label} ${formatPercent(value)}`)}"></span>`;
    })
    .join("");
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return `${Math.round(Number(value) * 100)}%`;
}

function formatTriple(cpu, memory, disk) {
  return `CPU ${formatPercent(cpu)} · RAM ${formatPercent(memory)} · Disk ${formatPercent(disk)}`;
}

function formatGroupConfig(group) {
  const cpu = group.configured_cpu_cores != null ? `${compact(group.configured_cpu_cores)} vCPU` : "n/a";
  const memory = group.configured_memory_gb != null ? `${compact(group.configured_memory_gb)} GiB` : "n/a";
  return `${cpu} · ${memory}`;
}

function formatLoadavg(values) {
  if (!Array.isArray(values) || !values.length) return "n/a";
  return values.map((item) => Number(item).toFixed(2)).join(" / ");
}

function compact(value) {
  const numeric = Number(value || 0);
  return numeric % 1 === 0 ? `${numeric}` : numeric.toFixed(1);
}

function formatDateTime(value) {
  try {
    return new Intl.DateTimeFormat("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(value));
  } catch {
    return String(value || "");
  }
}

function setLoading(isLoading) {
  if (analyticsElements.loading) analyticsElements.loading.hidden = !isLoading;
  if (analyticsElements.content) analyticsElements.content.hidden = isLoading;
}

function showError(message) {
  if (!analyticsElements.error) return;
  analyticsElements.error.hidden = false;
  analyticsElements.error.textContent = message;
}

function clearError() {
  if (!analyticsElements.error) return;
  analyticsElements.error.hidden = true;
  analyticsElements.error.textContent = "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
