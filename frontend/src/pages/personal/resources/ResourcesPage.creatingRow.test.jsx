// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import ResourcesPage from "./ResourcesPage";
import { withQueryClient } from "../../../queries/testing";

/**
 * 建立中佔位列：立即模式送出時後端把 start_at 設成送出當下，排進 worker 之前
 * provisioning_status 仍是 idle。曾因此一送出就顯示「超時 (0 分鐘)」，
 * 而且「到期日」欄放的是開始時間，看起來像機器馬上到期。
 */

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  listMySessions: vi.fn(),
  listRequests: vi.fn(),
  t: (key) => key,
}));

vi.mock("../../../services/resources", () => ({ ResourcesService: { list: mocks.list } }));
vi.mock("../../../services/quickPractice", () => ({ QuickPracticeService: { listMySessions: mocks.listMySessions } }));
vi.mock("../../../services/vmRequests", () => ({ VmRequestsService: { list: mocks.listRequests } }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...await importOriginal(),
  useTranslation: () => ({ t: mocks.t }),
}));
vi.mock("../../../contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1", role: "admin" } }) }));
vi.mock("../../../hooks/useToast", () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));
vi.mock("../../../components/ConfirmDialog/ConfirmProvider", () => ({ useConfirm: () => vi.fn() }));
vi.mock("../../../components/PageHeader/PageHeader", () => ({ default: () => null }));
vi.mock("../../../components/QuotaUsageBar/QuotaUsageBar", () => ({ default: () => null }));
vi.mock("../../../components/MachineKindBadge/MachineKindBadge", () => ({ default: () => null }));

const NOW = new Date("2026-10-29T03:00:00Z");

let root;
let host;

async function flush() {
  await act(async () => {
    /* TanStack Query 以 macrotask 批次通知，先等一個 timer tick */
    await new Promise((resolve) => setTimeout(resolve, 0));
    for (let i = 0; i < 5; i += 1) await Promise.resolve();
  });
}

function approvedRequest(overrides) {
  return {
    id: "req-1",
    hostname: "admin-vm",
    resource_type: "vm",
    cores: 2,
    memory: 2048,
    status: "approved",
    vmid: null,
    provisioning_status: "idle",
    created_at: "2026-10-29T02:59:50Z",
    start_at: "2026-10-29T02:59:50Z",
    end_at: null,
    expiry_date: null,
    ...overrides,
  };
}

async function renderCreatingRow(request) {
  mocks.listRequests.mockResolvedValue({ data: [request] });
  await act(async () => { root.render(withQueryClient(<ResourcesPage />)); });
  await flush();
  return [...host.querySelectorAll("tr")].find((tr) => tr.textContent.includes(request.hostname));
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  mocks.list.mockResolvedValue([]);
  mocks.listMySessions.mockResolvedValue([]);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
});

describe("ResourcesPage creating row", () => {
  test("an immediate request that was just submitted is not shown as overdue", async () => {
    const row = await renderCreatingRow(approvedRequest());

    expect(row.textContent).not.toContain("CreatingRow.statusOverdue");
    expect(row.textContent).toContain("CreatingRow.statusScheduling");
  });

  test("a request still waiting long after its start time is shown as overdue", async () => {
    const row = await renderCreatingRow(approvedRequest({ start_at: "2026-10-29T02:30:00Z" }));

    expect(row.textContent).toContain("CreatingRow.statusOverdue");
  });

  test("the expiry column shows no end instead of the start time for an open-ended request", async () => {
    const row = await renderCreatingRow(approvedRequest());

    expect(row.textContent).toContain("ResourceRow.unlimited");
    expect(row.textContent).not.toContain("2026/10/29");
  });

  test("the expiry column shows the end of the requested window", async () => {
    const row = await renderCreatingRow(approvedRequest({ end_at: "2026-12-31T12:00:00Z" }));

    expect(row.textContent).toContain("2026/12/31");
    expect(row.textContent).not.toContain("2026/10/29");
  });
});
