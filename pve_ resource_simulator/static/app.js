const HOURS_IN_DAY = 24;

const state = {
  servers: [],
  vmList: [],
  historicalProfiles: [],
  historicalPeakHours: [],
  historicalHourlyPeaks: {},
  scenarioSource: "default",
  scenarioNote: "",
  result: null,
  currentHour: 9,
  currentStep: 0,
  selectedRange: { start: 9, end: 12 },
};

const elements = {
  form: document.querySelector("#vm-form"),
  name: document.querySelector("#vm-name"),
  cpu: document.querySelector("#vm-cpu"),
  ram: document.querySelector("#vm-ram"),
  disk: document.querySelector("#vm-disk"),
  startHour: document.querySelector("#vm-start-hour"),
  endHour: document.querySelector("#vm-end-hour"),
  slotSummary: document.querySelector("#slot-summary"),
  reset: document.querySelector("#reset-all"),
  vmList: document.querySelector("#vm-list"),
  vmCount: document.querySelector("#vm-count"),
  errorBanner: document.querySelector("#error-banner"),
  dayCalendar: document.querySelector("#day-calendar"),
  calculationTableBody: document.querySelector("#calculation-table-body"),
  hourSummary: document.querySelector("#hour-summary"),
  slider: document.querySelector("#step-slider"),
  stepLabel: document.querySelector("#step-label"),
  stepCaption: document.querySelector("#step-caption"),
  serverBoard: document.querySelector("#server-board"),
  scenarioNote: document.querySelector("#scenario-note"),
};

elements.form?.addEventListener("submit", (event) => {
  event.preventDefault();
  void addVmFromForm();
});
elements.reset?.addEventListener("click", resetAll);
elements.startHour?.addEventListener("change", handleRangeChange);
elements.endHour?.addEventListener("change", handleRangeChange);
elements.slider?.addEventListener("input", (event) => {
  state.currentStep = Number(event.target.value || 0);
  renderCalculationTable();
  renderHourPanel();
  renderServerBoard();
});

void init();

async function init() {
  await loadScenario();
  renderScenarioNote();
  renderRangeControls();
  renderVmList();
  renderDayCalendar();
  renderCalculationTable();
  renderHourPanel();
  renderServerBoard();
}

async function loadScenario() {
  clearError();

  try {
    const liveResponse = await fetch("/api/v1/scenario/live");
    const livePayload = await liveResponse.json();
    if (!liveResponse.ok) {
      throw new Error(livePayload.detail || "Failed to load live scenario.");
    }
    applyScenario(livePayload);
    return;
  } catch (error) {
    console.warn("Live scenario unavailable, fallback to default scenario.", error);
  }

  const response = await fetch("/api/v1/scenario/default");
  const payload = await response.json();
  applyScenario(payload);
}

function applyScenario(payload) {
  state.servers = payload.servers || [];
  state.historicalProfiles = payload.historical_profiles || [];
  state.historicalPeakHours = payload.historical_peak_hours || [];
  state.historicalHourlyPeaks = payload.historical_hourly_peaks || {};
  state.scenarioSource = payload.source || "default";
  state.scenarioNote = payload.note || "";
  state.vmList = [];
  state.result = null;
}

function renderScenarioNote() {
  if (!elements.scenarioNote) return;
  const prefix = state.scenarioSource === "live"
    ? "目前使用真實 PVE node 狀態與同類型歷史平均進行模擬。"
    : "目前使用靜態示範資料，未接上真實 PVE。";
  elements.scenarioNote.textContent = `${prefix} ${state.scenarioNote}`.trim();
}

function handleRangeChange() {
  const start = Number(elements.startHour?.value || 0);
  const end = Number(elements.endHour?.value || 0);
  state.selectedRange = { start, end };
  renderRangeControls();
}

function renderRangeControls() {
  renderRangeSelects();

  if (!elements.slotSummary) return;

  if (!isValidRange(state.selectedRange.start, state.selectedRange.end)) {
    elements.slotSummary.textContent = "結束時段必須大於開始時段。";
    return;
  }

  elements.slotSummary.textContent = `${formatRange(state.selectedRange.start, state.selectedRange.end)} · ${state.selectedRange.end - state.selectedRange.start} hr`;
}

function renderRangeSelects() {
  if (elements.startHour) {
    elements.startHour.innerHTML = Array.from({ length: HOURS_IN_DAY }, (_, hour) => {
      const selected = state.selectedRange.start === hour ? "selected" : "";
      return `<option value="${hour}" ${selected}>${formatHour(hour)}</option>`;
    }).join("");
  }

  if (elements.endHour) {
    elements.endHour.innerHTML = Array.from({ length: HOURS_IN_DAY }, (_, index) => {
      const hour = index + 1;
      const selected = state.selectedRange.end === hour ? "selected" : "";
      return `<option value="${hour}" ${selected}>${formatHour(hour % HOURS_IN_DAY, hour === HOURS_IN_DAY)}</option>`;
    }).join("");
  }
}

async function addVmFromForm() {
  clearError();

  const cpu = Number(elements.cpu?.value || 0);
  const ram = Number(elements.ram?.value || 0);
  const disk = Number(elements.disk?.value || 0);
  const { start, end } = state.selectedRange;
  const activeHours = expandRange(start, end);
  const defaultName = `vm-${String(state.vmList.length + 1).padStart(3, "0")}`;
  const name = (elements.name?.value || "").trim() || defaultName;

  if (cpu <= 0 || ram <= 0 || disk <= 0) {
    showError("CPU、RAM、Disk 都必須大於 0。");
    return;
  }

  if (!isValidRange(start, end)) {
    showError("啟用時段無效，請重新選擇。");
    return;
  }

  state.vmList.push({
    id: `vm-${Date.now()}-${state.vmList.length + 1}`,
    name,
    cpu_cores: cpu,
    memory_gb: ram,
    disk_gb: disk,
    gpu_count: 0,
    active_hours: activeHours,
    enabled: true,
  });

  if (elements.name) elements.name.value = "";
  if (elements.cpu) elements.cpu.value = "2";
  if (elements.ram) elements.ram.value = "4";
  if (elements.disk) elements.disk.value = "40";

  state.result = null;
  state.currentStep = 0;
  renderVmList();
  renderDayCalendar();
  await runSimulation();
}

async function removeVm(index) {
  state.vmList.splice(index, 1);
  state.result = null;
  state.currentStep = 0;
  renderVmList();
  renderDayCalendar();
  renderCalculationTable();

  if (state.vmList.length) {
    await runSimulation();
    return;
  }

  renderHourPanel();
  renderServerBoard();
}

function resetAll() {
  state.vmList = [];
  state.result = null;
  state.currentHour = 9;
  state.currentStep = 0;
  state.selectedRange = { start: 9, end: 12 };
  clearError();
  renderRangeControls();
  renderVmList();
  renderDayCalendar();
  renderCalculationTable();
  renderHourPanel();
  renderServerBoard();
}

function renderVmList() {
  if (elements.vmCount) {
    elements.vmCount.textContent = `${state.vmList.length} 台`;
  }

  if (!elements.vmList) return;

  if (!state.vmList.length) {
    elements.vmList.innerHTML = `
      <div class="vm-item empty-state">
        <div class="vm-main">
          <p class="vm-spec">新增待申請 VM 後，系統會優先使用真實 PVE 的同類型歷史平均換算有效 CPU / RAM，沒有歷史就退回保守申請值。</p>
        </div>
      </div>
    `;
    return;
  }

  elements.vmList.innerHTML = state.vmList
    .map((vm, index) => {
      const historyHint = findProfileHint(vm);
      return `
        <article class="vm-item">
          <div class="vm-main">
            <p class="vm-name">${escapeHtml(vm.name)}</p>
            <p class="vm-spec">CPU ${formatCompact(vm.cpu_cores)} · RAM ${formatCompact(vm.memory_gb)} GB · Disk ${formatCompact(vm.disk_gb)} GB</p>
            <p class="vm-slot-line">${escapeHtml(formatHoursAsSingleRange(vm.active_hours || []))}</p>
            <p class="vm-slot-line">${escapeHtml(historyHint)}</p>
          </div>
          <button class="link-button" type="button" data-remove-index="${index}">移除</button>
        </article>
      `;
    })
    .join("");

  elements.vmList.querySelectorAll("[data-remove-index]").forEach((button) => {
    button.addEventListener("click", async () => {
      await removeVm(Number(button.getAttribute("data-remove-index")));
    });
  });
}

function findProfileHint(vm) {
  const match = state.historicalProfiles.find((profile) =>
    Number(profile.configured_cpu_cores) === Number(vm.cpu_cores)
    && Number(profile.configured_memory_gb) === Number(vm.memory_gb),
  );
  if (!match) {
    return "No matching history: use conservative requested CPU / RAM.";
  }
  return `Historical type match: ${match.type_label} from ${match.guest_count} real guest(s).`;
}

async function runSimulation() {
  clearError();

  try {
    const response = await fetch("/api/v1/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        servers: state.servers,
        vm_templates: state.vmList,
        historical_profiles: state.historicalProfiles,
      }),
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Simulation failed.");
    }

    state.result = payload;
    const firstActiveHour = payload.summary?.active_hours?.[0];
    const currentHourLoad = Number(payload.summary?.reservations_by_hour?.[String(state.currentHour)] || 0);
    if (typeof firstActiveHour === "number" && currentHourLoad === 0) {
      state.currentHour = firstActiveHour;
    }
    syncSliderToHourEnd();
    renderDayCalendar();
    renderCalculationTable();
    renderHourPanel();
    renderServerBoard();
  } catch (error) {
    showError(error.message || "Simulation failed.");
  }
}

function renderDayCalendar() {
  if (!elements.dayCalendar) return;

  const reservations = state.result?.summary?.reservations_by_hour || buildHourCountsFromVmList();
  const counts = Array.from({ length: HOURS_IN_DAY }, (_, hour) => Number(reservations[String(hour)] || 0));
  const peakCount = Math.max(...counts, 0);
  const useHistoricalPeak = peakCount === 0 && state.historicalPeakHours.length > 0;

  elements.dayCalendar.innerHTML = Array.from({ length: HOURS_IN_DAY }, (_, hour) => {
    const count = counts[hour];
    const selected = state.currentHour === hour;
    const busy = count > 0;
    const historicalPeakValue = state.historicalHourlyPeaks[String(hour)];
    const isPeak = useHistoricalPeak
      ? state.historicalPeakHours.includes(hour)
      : peakCount > 0 && count === peakCount;
    const peakTitle = useHistoricalPeak
      ? "Historical PVE peak hour."
      : `Peak hour with ${count} active VM reservation(s).`;
    return `
      <button
        class="calendar-hour ${selected ? "selected" : ""} ${busy ? "busy" : ""} ${isPeak ? "peak" : ""}"
        type="button"
        data-hour-select="${hour}"
        title="${isPeak ? peakTitle : `${count} active VM reservation(s).`}"
      >
        <span class="calendar-label-row">
          <span class="calendar-label">${formatHour(hour)}</span>
          ${isPeak ? `<span class="calendar-peak-pill">${useHistoricalPeak ? "PVE PEAK" : "PEAK"}</span>` : ""}
        </span>
        <span class="calendar-value-row">
          <span class="calendar-count">${count}</span>
          <span class="calendar-peak-value">${formatCalendarPeakValue(historicalPeakValue)}</span>
        </span>
      </button>
    `;
  }).join("");

  elements.dayCalendar.querySelectorAll("[data-hour-select]").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentHour = Number(button.getAttribute("data-hour-select"));
      syncSliderToHourEnd();
      renderDayCalendar();
      renderCalculationTable();
      renderHourPanel();
      renderServerBoard();
    });
  });
}

function renderCalculationTable() {
  if (!elements.calculationTableBody) return;

  const calculations = getCurrentHourResult()?.calculations || [];
  if (!calculations.length) {
    elements.calculationTableBody.innerHTML = `
      <tr>
        <td colspan="10" class="guest-empty">This hour has no active VM reservation.</td>
      </tr>
    `;
    return;
  }

  elements.calculationTableBody.innerHTML = calculations
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.vm_name)}</td>
          <td>${formatCompact(row.requested_cpu_cores)}C / ${formatCompact(row.requested_memory_gb)}G / ${formatCompact(row.requested_disk_gb)}D</td>
          <td>${escapeHtml(row.profile_label || "Fallback")}</td>
          <td>${formatRatioSource(row.cpu_ratio, row.source)}</td>
          <td>${formatRatioSource(row.memory_ratio, row.source)}</td>
          <td>${formatCompact(row.effective_cpu_cores)}C / ${formatCompact(row.effective_memory_gb)}G</td>
          <td>${formatCompact(row.peak_cpu_cores)}C / ${formatCompact(row.peak_memory_gb)}G</td>
          <td><span class="risk-pill ${peakRiskClass(row.peak_risk)}">${escapeHtml(formatPeakRisk(row.peak_risk))}</span></td>
          <td>${escapeHtml(formatPlacementStatus(row.placement_status))}</td>
          <td>${escapeHtml(row.placed_server_name || "-")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderHourPanel() {
  const currentHourResult = getCurrentHourResult();

  if (!currentHourResult) {
    if (elements.hourSummary) {
      elements.hourSummary.textContent = `${formatRange(state.currentHour, state.currentHour + 1)} · 沒有待放置 VM`;
    }
    if (elements.stepLabel) {
      elements.stepLabel.textContent = "逐步放置 VM";
    }
    if (elements.stepCaption) {
      elements.stepCaption.textContent = "新增 VM 後，系統會依照真實 PVE node 現況與同類型歷史平均重新計算放置結果。";
    }
    syncSlider();
    return;
  }

  const placed = currentHourResult.summary?.total_placements || 0;
  const requested = currentHourResult.summary?.requested_vm_count || 0;
  const failed = currentHourResult.summary?.failed_vm_names || [];

  if (elements.hourSummary) {
    elements.hourSummary.textContent = `${currentHourResult.label} · ${requested} 台待放置 · ${placed} 台成功${failed.length ? ` · ${failed.length} 台未放入` : ""}`;
  }

  const currentState = currentHourResult.states[state.currentStep] || currentHourResult.states[0];
  const lastStep = Math.max((currentHourResult.states?.length || 1) - 1, 0);

  if (elements.stepLabel) {
    elements.stepLabel.textContent = lastStep === 0
      ? `${currentHourResult.label} · 初始狀態`
      : `${currentState?.title || currentHourResult.label} · Step ${state.currentStep}/${lastStep}`;
  }

  if (elements.stepCaption) {
    elements.stepCaption.textContent = currentState?.latest_placement?.reason
      || currentHourResult.summary?.stop_reason
      || "目前沒有可顯示的放置說明。";
  }

  syncSlider();
}

function renderServerBoard() {
  if (!elements.serverBoard) return;

  const currentHourResult = getCurrentHourResult();
  const servers = currentHourResult?.states?.length
    ? currentHourResult.states[state.currentStep]?.servers
    : state.servers.map((server) => ({
        name: server.name,
        total: {
          cpu_cores: Number(server.cpu_cores || 0),
          memory_gb: Number(server.memory_gb || 0),
          disk_gb: Number(server.disk_gb || 0),
        },
        used: {
          cpu_cores: Number(server.cpu_used || 0),
          memory_gb: Number(server.memory_used_gb || 0),
          disk_gb: Number(server.disk_used_gb || 0),
        },
        remaining: {
          cpu_cores: Number(server.cpu_cores) - Number(server.cpu_used || 0),
          memory_gb: Number(server.memory_gb) - Number(server.memory_used_gb || 0),
          disk_gb: Number(server.disk_gb) - Number(server.disk_used_gb || 0),
        },
        vm_stack: [],
      }));

  elements.serverBoard.innerHTML = (servers || [])
    .map(
      (server) => `
        <article class="server-column">
          <div class="stack-frame">
            <div class="stack-cap">${escapeHtml(server.name)}</div>
            <div class="stack-body">
              ${renderVmStack(server.vm_stack)}
            </div>
          </div>
          <div class="server-footer">
            <h3>${escapeHtml(server.name)}</h3>
            <p class="server-meta">${escapeHtml(formatServerMeta(server))}</p>
          </div>
        </article>
      `,
    )
    .join("");
}

function formatServerMeta(server) {
  const cpuPhysicalFree = Math.max(
    Number(server.total?.cpu_cores || 0) - Number(server.used?.cpu_cores || 0),
    0,
  );
  const memoryPhysicalFree = Math.max(
    Number(server.total?.memory_gb || 0) - Number(server.used?.memory_gb || 0),
    0,
  );
  const cpuPolicyFree = Math.max(Number(server.remaining?.cpu_cores || 0), 0);
  const memoryPolicyFree = Math.max(Number(server.remaining?.memory_gb || 0), 0);
  const diskFree = Math.max(Number(server.remaining?.disk_gb || 0), 0);

  return [
    `CPU ${formatCompact(cpuPhysicalFree)} physical free / ${formatCompact(cpuPolicyFree)} policy`,
    `RAM ${formatCompact(memoryPhysicalFree)} physical free / ${formatCompact(memoryPolicyFree)} safe`,
    `Disk ${formatCompact(diskFree)} free`,
  ].join(" | ");
}

function syncSlider() {
  if (!elements.slider) return;

  const currentHourResult = getCurrentHourResult();
  if (!currentHourResult?.states?.length) {
    elements.slider.min = "0";
    elements.slider.max = "0";
    elements.slider.value = "0";
    elements.slider.disabled = true;
    return;
  }

  const max = currentHourResult.states.length - 1;
  state.currentStep = Math.min(state.currentStep, max);
  elements.slider.min = "0";
  elements.slider.max = String(max);
  elements.slider.value = String(state.currentStep);
  elements.slider.disabled = false;
}

function syncSliderToHourEnd() {
  const currentHourResult = getCurrentHourResult();
  state.currentStep = Math.max((currentHourResult?.states?.length || 1) - 1, 0);
  syncSlider();
}

function renderVmStack(vmStack) {
  if (!Array.isArray(vmStack) || vmStack.length === 0) {
    return `<div class="stack-empty">empty</div>`;
  }

  return vmStack
    .map(
      (item) => `
        <div class="stack-row">
          <span class="stack-name">${escapeHtml(item.name)}</span>
          <span class="stack-count">×${item.count}</span>
        </div>
      `,
    )
    .join("");
}

function getCurrentHourResult() {
  return state.result?.hours?.[state.currentHour] || null;
}

function buildHourCountsFromVmList() {
  const counts = {};
  for (let hour = 0; hour < HOURS_IN_DAY; hour += 1) {
    counts[String(hour)] = state.vmList.filter((vm) => (vm.active_hours || []).includes(hour)).length;
  }
  return counts;
}

function expandRange(start, end) {
  if (!isValidRange(start, end)) {
    return [];
  }
  return Array.from({ length: end - start }, (_, index) => start + index);
}

function isValidRange(start, end) {
  return Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end <= HOURS_IN_DAY && end > start;
}

function formatHour(hour, isEndOfDay = false) {
  if (hour === 0 && isEndOfDay) {
    return "24:00";
  }
  return `${String(hour).padStart(2, "0")}:00`;
}

function formatRange(start, end) {
  return `${formatHour(start)}-${formatHour(end % HOURS_IN_DAY, end === HOURS_IN_DAY)}`;
}

function formatHoursAsSingleRange(hours) {
  if (!Array.isArray(hours) || !hours.length) {
    return "No schedule";
  }
  const sorted = [...new Set(hours)].sort((left, right) => left - right);
  return formatRange(sorted[0], sorted[sorted.length - 1] + 1);
}

function formatCompact(value) {
  const numeric = Number(value || 0);
  return numeric % 1 === 0 ? String(numeric) : numeric.toFixed(1);
}

function formatRatioSource(value, source) {
  if (value == null) {
    return source === "requested" ? "fallback" : "n/a";
  }
  const percentage = Number(value) * 100;
  if (percentage > 0 && percentage < 1) {
    return "<1%";
  }
  if (percentage < 10) {
    return `${percentage.toFixed(1)}%`;
  }
  return `${Math.round(percentage)}%`;
}

function formatPlacementStatus(status) {
  if (status === "placed") return "Placed";
  if (status === "no_fit") return "No fit";
  return "Pending";
}

function formatCalendarPeakValue(value) {
  if (value == null) {
    return "Peak --";
  }
  const percentage = Number(value) * 100;
  if (percentage > 0 && percentage < 1) {
    return "Peak <1%";
  }
  if (percentage < 10) {
    return `Peak ${percentage.toFixed(1)}%`;
  }
  return `Peak ${Math.round(percentage)}%`;
}

function formatPeakRisk(risk) {
  if (risk === "safe") return "Safe";
  if (risk === "guarded") return "Guarded";
  if (risk === "high") return "High";
  if (risk === "n/a") return "n/a";
  return "Pending";
}

function peakRiskClass(risk) {
  if (risk === "safe") return "is-safe";
  if (risk === "guarded") return "is-guarded";
  if (risk === "high") return "is-high";
  return "is-neutral";
}

function showError(message) {
  if (!elements.errorBanner) return;
  elements.errorBanner.hidden = false;
  elements.errorBanner.textContent = message;
}

function clearError() {
  if (!elements.errorBanner) return;
  elements.errorBanner.hidden = true;
  elements.errorBanner.textContent = "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
