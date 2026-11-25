// @vitest-environment happy-dom
/* 窄版收欄（useTableFit）：表格區變窄時，次要欄收進名稱欄與狀態欄，導覽錨點與 PCI 展開鈕跟著搬，
   展開的完整位址列橫跨目前顯示中的欄 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { withQueryClient } from "../../../queries/testing";
import GpuMgmtPage from "./GpuMgmtPage";

const mocks = vi.hoisted(() => ({
  listMappings: vi.fn(),
  t: (key) => key,
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../../../services/gpu", () => ({ GpuService: { listMappings: mocks.listMappings, deleteMapping: vi.fn() } }));
vi.mock("react-i18next", async (importOriginal) => ({ ...await importOriginal(), useTranslation: () => ({ t: mocks.t }) }));
vi.mock("../../../hooks/useToast", () => ({ useToast: () => mocks.toast }));
vi.mock("../../../components/ConfirmDialog/ConfirmProvider", () => ({ useConfirm: () => vi.fn() }));
vi.mock("../../../components/PageHeader/PageHeader", () => ({ default: () => null }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const originalClientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
let tableWidth;
let host;
let root;

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
    for (let i = 0; i < 5; i += 1) await Promise.resolve();
  });
}

beforeEach(() => {
  mocks.listMappings.mockReset();
  /* happy-dom 沒有版面：表格區（data-guide="gpu-mgmt-table"）的寬度由測試指定 */
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() { return this.getAttribute("data-guide") === "gpu-mgmt-table" ? tableWidth : 0; },
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  if (originalClientWidth) Object.defineProperty(HTMLElement.prototype, "clientWidth", originalClientWidth);
});

/* 四個 VF：超過收合門檻，PCI 欄是區段摘要＋展開鈕 */
const MAPPING = {
  id: "a100-lab",
  description: "NVIDIA A100",
  maps: ["0000:41:00.1", "0000:41:00.2", "0000:41:00.3", "0000:41:00.4"].map((path, index) => ({ node: "pve-01", path, id: String(index) })),
  device_count: 4,
  capacity_count: 4,
  used_count: 1,
  available_count: 3,
  is_sriov: true,
  used_by: [{ vmid: 101, vm_name: "train-01", status: "running" }],
};

async function renderAt(width) {
  tableWidth = width;
  mocks.listMappings.mockResolvedValue({ data: [MAPPING] });
  await act(async () => { root.render(withQueryClient(<GpuMgmtPage />)); });
  await flush();
}

const headers = () => [...host.querySelectorAll("thead th")].map((th) => th.textContent);
const firstRowCells = () => [...host.querySelector("tbody tr").children];

test("at 1440 (about 1003px) only the description folds, under the mapping name", async () => {
  await renderAt(1003);
  expect(headers()).not.toContain("GpuMgmtPage.columnDescription");
  expect(headers()).toHaveLength(6);
  expect(firstRowCells()[0].textContent).toContain("NVIDIA A100");
});

test("at 1440 with the AI assistant open (567px) PCI goes under the name and capacity/VMs under the status", async () => {
  await renderAt(567);
  expect(headers()).toEqual(["GpuMgmtPage.columnMapping", "GpuMgmtPage.columnStatus", "GpuMgmtPage.columnActions"]);
  expect(host.querySelector("table").hasAttribute("data-overflow")).toBe(false);

  const [nameCell, statusCell, actionsCell] = firstRowCells();
  expect(nameCell.querySelector('[data-guide="gpu-mgmt-pci"]')).not.toBeNull();
  expect(statusCell.querySelector('[data-guide="gpu-mgmt-capacity"]').textContent).toContain("GpuMgmtPage.columnAvailableTotal 3 / 4");
  expect(statusCell.querySelector('[data-guide="gpu-mgmt-usage"]').textContent).toContain("train-01");
  expect(actionsCell.getAttribute("data-guide")).toBe("gpu-mgmt-delete");

  /* 收進名稱欄的展開鈕照樣能展開；完整位址列只橫跨顯示中的三欄 */
  await act(async () => { nameCell.querySelector("button[aria-expanded]").click(); });
  const detailCell = host.querySelectorAll("tbody tr")[1].querySelector("td");
  expect(detailCell.colSpan).toBe(3);
  expect(detailCell.textContent).toContain("0000:41:00.4");
});

test("on a phone (448px) the fully folded table still fits without scrolling", async () => {
  await renderAt(448);
  expect(headers()).toHaveLength(3);
  expect(host.querySelector("table").hasAttribute("data-overflow")).toBe(false);
});

/* 整張卡直通的八張卡：位址不連續、壓不成區段，摘要只留節點，位址展開才看得到 */
test("scattered addresses collapse to the node name until expanded", async () => {
  const paths = ["06", "08", "09", "0a", "0e", "0f", "10", "11"].map((bus) => `0000:${bus}:00`);
  tableWidth = 1400;
  mocks.listMappings.mockResolvedValue({
    data: [{ ...MAPPING, is_sriov: false, device_count: 8, capacity_count: 8, maps: paths.map((path, index) => ({ node: "pve19", path, id: String(index) })) }],
  });
  await act(async () => { root.render(withQueryClient(<GpuMgmtPage />)); });
  await flush();

  const pciCell = host.querySelector('[data-guide="gpu-mgmt-pci"]');
  expect(pciCell.textContent).toContain("pve19");
  expect(pciCell.textContent.match(/pve19/g)).toHaveLength(1);
  expect(pciCell.textContent).not.toContain("0000:");

  await act(async () => { pciCell.querySelector("button[aria-expanded]").click(); });
  expect(host.querySelectorAll("tbody tr")[1].textContent).toContain("0000:11:00");
});
