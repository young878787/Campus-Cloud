const HOURS_IN_DAY = 24;

const state = {
  servers: [],
  vmList: [],
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
  hourSummary: document.querySelector("#hour-summary"),
  slider: document.querySelector("#step-slider"),
  stepLabel: document.querySelector("#step-label"),
  stepCaption: document.querySelector("#step-caption"),
  serverBoard: document.querySelector("#server-board"),
};

elements.form?.addEventListener("submit", (event) => {
  event.preventDefault();
  addVmFromForm();
});
elements.reset?.addEventListener("click", resetAll);
elements.startHour?.addEventListener("change", handleRangeChange);
elements.endHour?.addEventListener("change", handleRangeChange);
elements.slider?.addEventListener("input", (event) => {
  state.currentStep = Number(event.target.value || 0);
  renderHourPanel();
  renderServerBoard();
});

init();

async function init() {
  await loadDefaultScenario();
  renderRangeControls();
  renderVmList();
  renderDayCalendar();
  renderHourPanel();
  renderServerBoard();
}

async function loadDefaultScenario() {
  clearError();
  const response = await fetch("/api/v1/scenario/default");
  const payload = await response.json();
  state.servers = payload.servers || [];
  state.vmList = [];
  state.result = null;
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
    elements.slotSummary.textContent = "結束時間需晚於開始時間";
    return;
  }

  elements.slotSummary.textContent = `${formatRange(state.selectedRange.start, state.selectedRange.end)} · ${state.selectedRange.end - state.selectedRange.start}hr`;
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
    showError("預約時段必須是單一連續區間，且結束時間要晚於開始時間。");
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
          <p class="vm-spec">目前還沒有 VM 預約，先在上方填表單與單一時段。</p>
        </div>
      </div>
    `;
    return;
  }

  elements.vmList.innerHTML = state.vmList
    .map(
      (vm, index) => `
        <article class="vm-item">
          <div class="vm-main">
            <p class="vm-name">${escapeHtml(vm.name)}</p>
            <p class="vm-spec">CPU ${formatCompact(vm.cpu_cores)} · RAM ${formatCompact(vm.memory_gb)} GB · Disk ${formatCompact(vm.disk_gb)} GB</p>
            <p class="vm-slot-line">${escapeHtml(formatHoursAsSingleRange(vm.active_hours || []))}</p>
          </div>
          <button class="link-button" type="button" data-remove-index="${index}">刪除</button>
        </article>
      `,
    )
    .join("");

  elements.vmList.querySelectorAll("[data-remove-index]").forEach((button) => {
    button.addEventListener("click", async () => {
      await removeVm(Number(button.getAttribute("data-remove-index")));
    });
  });
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
    renderHourPanel();
    renderServerBoard();
  } catch (error) {
    showError(error.message || "Simulation failed.");
  }
}

function renderDayCalendar() {
  if (!elements.dayCalendar) return;

  const reservations = state.result?.summary?.reservations_by_hour || buildHourCountsFromVmList();

  elements.dayCalendar.innerHTML = Array.from({ length: HOURS_IN_DAY }, (_, hour) => {
    const count = Number(reservations[String(hour)] || 0);
    const selected = state.currentHour === hour;
    const busy = count > 0;
    return `
      <button
        class="calendar-hour ${selected ? "selected" : ""} ${busy ? "busy" : ""}"
        type="button"
        data-hour-select="${hour}"
      >
        <span class="calendar-label">${formatHour(hour)}</span>
        <span class="calendar-count">${count}</span>
      </button>
    `;
  }).join("");

  elements.dayCalendar.querySelectorAll("[data-hour-select]").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentHour = Number(button.getAttribute("data-hour-select"));
      syncSliderToHourEnd();
      renderDayCalendar();
      renderHourPanel();
      renderServerBoard();
    });
  });
}

function renderHourPanel() {
  const currentHourResult = getCurrentHourResult();

  if (!currentHourResult) {
    if (elements.hourSummary) {
      elements.hourSummary.textContent = `${formatRange(state.currentHour, state.currentHour + 1)} · 尚未有預約`;
    }
    if (elements.stepLabel) {
      elements.stepLabel.textContent = "先新增 VM 預約";
    }
    if (elements.stepCaption) {
      elements.stepCaption.textContent = "每台 VM 只能設定一段連續時段，系統會逐 hour 自動模擬。";
    }
    syncSlider();
    return;
  }

  const placed = currentHourResult.summary?.total_placements || 0;
  const requested = currentHourResult.summary?.requested_vm_count || 0;
  const failed = currentHourResult.summary?.failed_vm_names || [];

  if (elements.hourSummary) {
    elements.hourSummary.textContent = `${currentHourResult.label} · ${requested} 個生效預約 · ${placed} 個已放入${failed.length ? ` · ${failed.length} 個未放入` : ""}`;
  }

  const currentState = currentHourResult.states[state.currentStep] || currentHourResult.states[0];
  const lastStep = Math.max((currentHourResult.states?.length || 1) - 1, 0);

  if (elements.stepLabel) {
    elements.stepLabel.textContent = lastStep === 0
      ? `${currentHourResult.label} · 無新增步驟`
      : `${currentState?.title || currentHourResult.label} · Step ${state.currentStep}/${lastStep}`;
  }

  if (elements.stepCaption) {
    elements.stepCaption.textContent = currentState?.latest_placement?.reason
      || currentHourResult.summary?.stop_reason
      || "這個時段目前沒有生效中的 VM。";
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
            <p class="server-meta">
              CPU ${formatCompact(server.remaining?.cpu_cores)} free ·
              RAM ${formatCompact(server.remaining?.memory_gb)} free ·
              Disk ${formatCompact(server.remaining?.disk_gb)} free
            </p>
          </div>
        </article>
      `,
    )
    .join("");
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
    return "未設定時段";
  }
  const sorted = [...new Set(hours)].sort((left, right) => left - right);
  return formatRange(sorted[0], sorted[sorted.length - 1] + 1);
}

function formatCompact(value) {
  const numeric = Number(value || 0);
  return numeric % 1 === 0 ? String(numeric) : numeric.toFixed(1);
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
