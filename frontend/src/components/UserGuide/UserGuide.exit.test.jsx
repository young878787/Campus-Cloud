// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import UserGuide from "./UserGuide";
import { USER_GUIDE_START_EVENT } from "./routeGuides";

const state = vi.hoisted(() => ({ user: null, updateUser: vi.fn(), markSeen: vi.fn() }));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => state }));
vi.mock("../../services/account", () => ({ AccountService: { markUserGuideSeen: state.markSeen } }));
vi.mock("react-router-dom", () => ({ useLocation: () => ({ pathname: "/my-requests" }) }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key) => key }) }));

let root;
let host;
let back;

/* 申請列表頁：按「建立申請」才把表單（含返回鈕）放進 DOM，跟真的頁面一樣 */
function mountRequestsPage() {
  document.body.innerHTML = '<h1>我的申請</h1><span data-user-guide-slot></span><div data-page-guide="header"></div>';
  const create = document.createElement("button");
  create.dataset.guide = "request-create";
  create.addEventListener("click", () => {
    const form = document.createElement("div");
    form.dataset.guide = "request-resource-settings";
    back = document.createElement("button");
    back.dataset.guide = "request-form-back";
    back.addEventListener("click", () => form.remove());
    form.append(back);
    document.body.append(form);
  });
  document.body.append(create);
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  localStorage.clear();
  sessionStorage.clear();
  state.user = { id: "u1", role: "student", seen_user_guides: [] };
  state.markSeen.mockReset().mockResolvedValue({ seen_user_guides: ["my-requests"] });
  state.updateUser.mockReset();
  mountRequestsPage();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  vi.useRealTimers();
  document.body.innerHTML = "";
});

/* 自動開導覽要等頁面目標出現（500ms 起跳），聚光框位置再等 360ms 的定位校正才會畫出面板。
   act 結束時才會重繪，所以分兩段推時間：先讓導覽打開，再讓聚光框定位 */
async function openGuide() {
  await act(async () => root.render(<UserGuide />));
  await act(async () => vi.advanceTimersByTimeAsync(600));
  await act(async () => vi.advanceTimersByTimeAsync(600));
}

const formOpen = () => Boolean(document.querySelector('[data-guide="request-resource-settings"]'));
const buttonByText = (text) => [...document.querySelectorAll("button")].find((button) => button.textContent === text);

test("導覽自己打開的申請表單，按「跳過導覽」會退回申請列表", async () => {
  await openGuide();
  expect(formOpen()).toBe(true);

  await act(async () => buttonByText("UserGuide.skipButton").click());
  expect(formOpen()).toBe(false);
});

test("使用者自己先打開表單，再跳過導覽時表單保留", async () => {
  document.querySelector('[data-guide="request-create"]').click();
  await openGuide();
  expect(formOpen()).toBe(true);

  await act(async () => buttonByText("UserGuide.skipButton").click());
  expect(formOpen()).toBe(true);
});

test("看過導覽後，外部入口（AI 助手）派發開始事件仍會打開導覽", async () => {
  state.user = { id: "u1", role: "student", seen_user_guides: ["my-requests"] };
  await openGuide();
  expect(buttonByText("UserGuide.skipButton")).toBeUndefined();

  await act(async () => window.dispatchEvent(new CustomEvent(USER_GUIDE_START_EVENT)));
  await act(async () => vi.advanceTimersByTimeAsync(600));
  await act(async () => vi.advanceTimersByTimeAsync(600));
  expect(buttonByText("UserGuide.skipButton")).toBeDefined();
});

test("導覽是 aria-modal 對話框：按 Esc 等同「跳過導覽」，關閉並退回申請列表", async () => {
  await openGuide();
  expect(buttonByText("UserGuide.skipButton")).toBeDefined();

  await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(buttonByText("UserGuide.skipButton")).toBeUndefined();
  expect(formOpen()).toBe(false);
});
