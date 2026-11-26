/**
 * 防火牆拓撲（/firewall）的拖拉互動（計畫 §5：F 系列）。
 *
 * 拓撲資料來自 fixtures：Internet、自己的 web-101 / db-102、班級的 class-103（不可管理）、
 * 一條 Internet → 101 的連線。動作集中在拖動節點、從 handle 拉線、對話框只按 Escape。
 */
import { actions, weighted, always, eventually, now } from "@antithesishq/bombadil";
import { extract } from "@antithesishq/bombadil/browser";
import { ACCOUNTS, goto, loginAs, onLogin, route } from "../lib/navigation.ts";
import { safeClicks } from "../lib/safety.ts";

export { noUncaughtExceptions, noUnhandledPromiseRejections, noServerErrors, noWriteAttempted } from "../properties/common.ts";

/** fixtures 的 VM（101、102 自己的，103 班級的） */
const FIXTURE_VMS = new Set(["101", "102", "103"]);
/** fixtures 的連線數 */
const FIXTURE_EDGES = 1;

const flow = extract((s) => {
  const pane = s.document.querySelector(".react-flow__pane")?.getBoundingClientRect();
  const nodes = Array.from(s.document.querySelectorAll(".react-flow__node")).map((n) => {
    const r = n.getBoundingClientRect();
    return {
      id: n.getAttribute("data-id") ?? "",
      type: Array.from(n.classList).find((c) => c.startsWith("react-flow__node-"))?.slice(17) ?? "",
      x: r.x, y: r.y, w: r.width, h: r.height,
      transform: (n as HTMLElement).style.transform,
    };
  });
  const handles = Array.from(s.document.querySelectorAll(".react-flow__handle.source")).map((h) => {
    const r = h.getBoundingClientRect();
    return { node: h.closest(".react-flow__node")?.getAttribute("data-id") ?? "", x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  return {
    pane: pane ? { x: pane.x, y: pane.y, w: pane.width, h: pane.height } : null,
    nodes,
    handles,
    edges: s.document.querySelectorAll(".react-flow__edge").length,
    dialog: !!s.document.querySelector("[role=dialog], [role=alertdialog]"),
  };
});

const onFirewall = () => route.current === "/firewall" && flow.current.pane !== null;
const vms = () => flow.current.nodes.filter((n) => n.type === "vm");

const { email, password } = ACCOUNTS.student;
export const login = actions(() => (onLogin.current ? [loginAs(email, password)] : []));
const go = actions(() => (route.current !== "/firewall" ? [goto("/firewall")] : []));

const drag = actions(() => {
  const p = flow.current.pane;
  if (!p) return [];
  return vms().map((n) => ({
    MouseDrag: {
      from: { x: n.x + n.w / 2, y: n.y + n.h / 2 },
      to: { x: [p.x + 40, p.x + p.w - 40] as [number, number], y: [p.y + 40, p.y + p.h - 40] as [number, number] },
      steps: 12,
      delayMillis: 15,
    },
  }));
});
const connect = actions(() => {
  const out: any[] = [];
  for (const h of flow.current.handles)
    for (const n of flow.current.nodes)
      if (n.id !== h.node && n.type !== "vmGroup")
        out.push({ MouseDrag: { from: { x: h.x, y: h.y }, to: { x: n.x + n.w / 2, y: n.y + n.h / 2 }, steps: 15, delayMillis: 15 } });
  return out;
});
const ESCAPE = 27;

/** 對話框開著時只能按 Escape；沒開時拖、拉線、點畫面上的安全元素 */
export const explore = weighted([
  [1, go],
  [6, drag.when(() => onFirewall() && !flow.current.dialog)],
  [6, connect.when(() => onFirewall() && !flow.current.dialog)],
  [3, safeClicks.when(() => onFirewall() && !flow.current.dialog)],
  [1, actions(() => ["Wait" as const])],
] as any).when(() => !onLogin.current && !flow.current.dialog);
export const closeDialog = actions(() => [{ PressKey: { code: ESCAPE } }]).when(() => flow.current.dialog);

/** F1：VM 節點不重複、都來自伺服器資料（篩選會減少節點，但拖拉、拉線不會變出或複製節點） */
export const vmNodesConsistent = always(() => {
  const ids = vms().map((n) => n.id);
  return new Set(ids).size === ids.length && ids.every((id) => FIXTURE_VMS.has(id));
});

/** F2：節點位置永遠是有限數字（拖到邊界、快速連續拖動不產生 NaN） */
export const nodePositionsFinite = always(() =>
  flow.current.nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y) && !/NaN|Infinity/.test(n.transform)),
);

/** F3：寫入被拒（409）後，連線數 5 秒內回到伺服器的狀態（不留下沒存成功的連線） */
export const edgesRollBack = always(
  now(() => onFirewall() && !flow.current.dialog && flow.current.edges !== FIXTURE_EDGES).implies(
    eventually(() => !onFirewall() || flow.current.dialog || flow.current.edges === FIXTURE_EDGES).within(5, "seconds"),
  ),
);

/** F4：對話框按 Escape 會在 3 秒內關閉 */
export const dialogClosesOnEscape = always(now(() => flow.current.dialog).implies(eventually(() => !flow.current.dialog).within(3, "seconds")));
