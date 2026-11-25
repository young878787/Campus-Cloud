import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import PixelSprite from "../PixelSprite";
import { ICONS, ICON_PALETTE } from "../icons";
import styles from "./Games.module.scss";
import { useEmit } from "./useEmit";

/* 拓撲座標（viewBox 560×260），節點按鈕用百分比疊在同一個位置 */
const W = 560;
const H = 260;
const WALL_X = 250;
const NODES = {
  internet: { x: 74, y: 130, icon: "globe" },
  web: { x: 474, y: 64, icon: "server" },
  db: { x: 474, y: 196, icon: "database" },
};
/* 要開的方向：外面進來（開放服務給外部）、機器之間（讓兩台機器互通）；預設只擋入站 */
const PAIRS = [
  ["internet", "web"],
  ["internet", "db"],
  ["web", "db"],
];
/* 導覽提示（data-act）：外面連網站＝網際網路的圓點 → web-01 → 發布；網站連資料庫＝web-01 的圓點 → db-01 → 填 3306 → 建立連線 */
const HANDLE_ACT = { internet: "web", web: "db" };
const NODE_ACT = { web: "web", db: "db" };
/* 開放服務給外部的三種方式（同實際的連線對話框）；用網址是預設：服務的內部 port 80，閘道處理 HTTPS */
const PUBLISH = ["url", "port", "fw"];
const SERVICE_PORT = 80;
const EXT_PORT = 10080;

/* 線上與防火牆交會的點（外面進來的封包撞到這裡彈回） */
function wallPoint(a, b) {
  const k = (WALL_X - a.x) / (b.x - a.x);
  return { x: WALL_X, y: a.y + (b.y - a.y) * k };
}

/**
 * 第 3 關：拉一條線開通連線，照實際的網路拓撲頁：
 *   從節點右邊的圓點拖一條線到另一台（鍵盤：按圓點再選目的地）→ 跳出連線對話框；
 *   網際網路 → 機器是「開放服務給外部」（用網址／用對外 port／僅開放防火牆，按「發布」），
 *   機器 → 機器是「讓兩台機器互通」（填連接埠，按「建立連線」）。規則自動寫好，外面進來沒拉線的一律擋下。
 *   點節點本身在實際系統是打開它的規則，這裡只提示要從圓點拉線。
 * 網站對外發布、網站連資料庫 3306、資料庫不外露就過關。
 * preview：示意畫面，兩條連線已經拉好（封包流過、往資料庫的被擋下）。
 */
export default function FirewallGame({ onWin, onEvent, preview = false }) {
  const emit = useEmit(onEvent);
  const { t } = useTranslation("pixel");
  const goals = t("firewall.goals", { returnObjects: true });
  const [rules, setRules] = useState(() =>
    preview
      ? [
          { from: "internet", to: "web", kind: "url", port: SERVICE_PORT, id: "internet-web" },
          { from: "web", to: "db", kind: "conn", port: 3306, id: "web-db-3306" },
        ]
      : [],
  );
  const [armed, setArmed] = useState(null); // 按了某台的圓點（不拖），等選目的地
  const [drag, setDrag] = useState(null); // { from, x, y }：拖線中，座標是 viewBox 的
  const [pending, setPending] = useState(null); // { from, to }：連線對話框
  const [mode, setMode] = useState("url");
  const [port, setPort] = useState("");
  const [note, setNote] = useState("");
  const topoRef = useRef(null);
  const moved = useRef(false);
  const won = useRef(false);

  const has = (from, to, p) => rules.some((r) => r.from === from && r.to === to && (!p || r.port === p));
  const g1 = has("internet", "web");
  const g2 = has("web", "db", 3306);
  const g3 = !has("internet", "db");
  const danger = !g3;

  /* 導覽用：外面連到網站、網站連到資料庫、三個條件都達成 */
  useEffect(() => {
    if (g1) emit("web");
  }, [g1, emit]);
  useEffect(() => {
    if (g2) emit("db");
  }, [g2, emit]);

  useEffect(() => {
    if (g1 && g2 && g3 && !won.current) {
      won.current = true;
      onWin?.();
    }
  }, [g1, g2, g3, onWin]);

  const label = (id) => (id === "internet" ? t("firewall.internet") : id === "web" ? "web-01" : "db-01");

  const connect = (from, to) => {
    setArmed(null);
    if (!PAIRS.some(([a, b]) => a === from && b === to)) {
      setNote(t("firewall.noPair", { from: label(from), to: label(to) }));
      return;
    }
    setNote("");
    setPending({ from, to });
    setMode("url");
    setPort("");
  };

  /* 拖線：在圓點上按下 → 移動畫虛線 → 放在哪台機器上就連到哪台 */
  const toView = (e) => {
    const r = topoRef.current.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H };
  };
  const onHandleDown = (id) => (e) => {
    if (e.button !== 0) return;
    moved.current = false;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // 合成事件（輔助工具、測試）沒有真的指標可以抓，照樣能拖
    }
    setPending(null);
    setDrag({ from: id, ...toView(e) });
  };
  const onHandleMove = (e) => {
    if (!drag) return;
    moved.current = true;
    const p = toView(e);
    setDrag((d) => d && { ...d, ...p });
  };
  const onHandleUp = (e) => {
    if (!drag) return;
    const { from } = drag;
    setDrag(null);
    if (!moved.current) return; // 沒拖動：當成點一下（交給 onClick）
    const target = document.elementFromPoint(e.clientX, e.clientY)?.closest("[data-node]")?.dataset.node;
    if (target && target !== from) connect(from, target);
  };
  const onHandleClick = (id) => () => {
    if (moved.current) {
      moved.current = false;
      return;
    }
    setPending(null);
    setNote("");
    setArmed((a) => (a === id ? null : id));
  };
  const onNodeClick = (id) => () => {
    if (armed && armed !== id) {
      connect(armed, id);
      return;
    }
    setArmed(null);
    setNote(t("firewall.nodeHint", { node: label(id) }));
  };

  const submit = (e) => {
    e.preventDefault();
    const { from, to } = pending;
    let rule;
    if (from === "internet") {
      rule = { from, to, kind: mode, port: SERVICE_PORT, id: `${from}-${to}` };
    } else {
      const p = Number(port);
      if (!p) return;
      rule = { from, to, kind: "conn", port: p, id: `${from}-${to}-${p}` };
    }
    setRules((prev) => [...prev.filter((r) => r.id !== rule.id), rule]);
    setPending(null);
  };

  const ruleText = (r) => {
    const args = { from: label(r.from), to: label(r.to), port: r.port, ext: EXT_PORT };
    return t(`firewall.rule.${r.kind}`, args);
  };
  const lineLabel = (r) => (r.kind === "url" ? "HTTPS" : r.kind === "port" ? `:${EXT_PORT}` : `:${r.port}`);

  let hint = note || t("firewall.hintSource");
  if (drag) hint = t("firewall.hintDrop");
  else if (armed) hint = t("firewall.hintTarget", { from: label(armed) });

  const pct = (n, total) => `${(n / total) * 100}%`;
  const fromInternet = pending?.from === "internet";
  const submitAct = pending && (pending.from === "internet" ? (pending.to === "web" ? "web" : undefined) : pending.to === "db" ? "db" : undefined);

  return (
    <div className={styles.game}>
      <ul className={styles.goals}>
        {goals.map((goal, i) => {
          const ok = [g1, g2, g3][i] && (i < 2 || (g1 && g2));
          return (
            <li key={goal} className={ok ? styles.goalOk : undefined}>
              <span aria-hidden="true">{ok ? "✓" : i + 1}</span>
              {goal}
            </li>
          );
        })}
      </ul>

      {/* 夠寬時規則清單放在拓撲圖右邊：拉完線馬上看得到自動產生的規則（筆電不用往下捲） */}
      <div className={styles.fwLayout}>
        <div className={styles.fwCols}>
          <div className={styles.fwMain}>
            <div className={styles.topo} data-danger={danger || undefined} ref={topoRef}>
              <svg viewBox={`0 0 ${W} ${H}`} className={styles.topoSvg} aria-hidden="true">
                {/* 防火牆：一道像素磚牆 */}
                {Array.from({ length: 13 }, (_, i) => (
                  <rect key={i} className={styles.brick} x={WALL_X - 9 + (i % 2) * 4} y={14 + i * 17} width="14" height="15" />
                ))}
                <text className={styles.wallLabel} x={WALL_X} y={H - 2}>{t("firewall.wall")}</text>

                {rules.map((r) => {
                  const a = NODES[r.from];
                  const b = NODES[r.to];
                  const bad = r.from === "internet" && r.to === "db";
                  return (
                    <g key={r.id} className={bad ? styles.ruleBad : styles.ruleOk}>
                      <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
                      <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 8}>{lineLabel(r)}</text>
                      <rect className={styles.packet} width="8" height="8" x="-4" y="-4">
                        <animateMotion dur="2.2s" repeatCount="indefinite" path={`M${a.x} ${a.y} L${b.x} ${b.y}`} />
                      </rect>
                    </g>
                  );
                })}

                {/* 外面進來、還沒有規則的連線：封包撞牆彈回 */}
                {["web", "db"].map((to) => {
                  if (has("internet", to)) return null;
                  const a = NODES.internet;
                  const p = wallPoint(a, NODES[to]);
                  return (
                    <g key={`blocked-${to}`} className={styles.blocked}>
                      <line x1={a.x} y1={a.y} x2={p.x} y2={p.y} />
                      <rect className={styles.packet} width="8" height="8" x="-4" y="-4">
                        <animateMotion
                          dur="1.8s"
                          repeatCount="indefinite"
                          keyPoints="0;1;0"
                          keyTimes="0;0.5;1"
                          calcMode="linear"
                          path={`M${a.x} ${a.y} L${p.x - 10} ${p.y}`}
                        />
                      </rect>
                    </g>
                  );
                })}

                {/* 拖線中的虛線 */}
                {drag && (
                  <line className={styles.dragLine} x1={NODES[drag.from].x} y1={NODES[drag.from].y} x2={drag.x} y2={drag.y} />
                )}
              </svg>

              {Object.entries(NODES).map(([id, node]) => (
                <div key={id} className={styles.topoSpot} style={{ left: pct(node.x, W), top: pct(node.y, H) }}>
                  <button
                    type="button"
                    data-node={id}
                    className={`${styles.topoNode} ${armed === id || drag?.from === id ? styles.topoNodeOn : ""}`}
                    onClick={onNodeClick(id)}
                    data-act={NODE_ACT[id]}
                  >
                    <PixelSprite rows={ICONS[node.icon]} palette={ICON_PALETTE} cell={3} />
                    <span>{label(id)}</span>
                  </button>
                  {/* 右邊的圓點：從這裡拉線（實際系統也是從節點右側的圓點拖曳） */}
                  <button
                    type="button"
                    className={styles.topoHandle}
                    aria-label={t("firewall.handleLabel", { node: label(id) })}
                    aria-pressed={armed === id}
                    onPointerDown={onHandleDown(id)}
                    onPointerMove={onHandleMove}
                    onPointerUp={onHandleUp}
                    onPointerCancel={() => setDrag(null)}
                    onClick={onHandleClick(id)}
                    data-act={HANDLE_ACT[id]}
                  />
                </div>
              ))}
            </div>

            {/* 示意畫面不顯示操作提示與對話框 */}
            {!preview &&
              (pending ? (
                <form className={styles.fwDialog} onSubmit={submit}>
                  <p className={styles.fwDialogTitle}>
                    {fromInternet
                      ? t("firewall.publishTitle", { to: label(pending.to) })
                      : t("firewall.connTitle", { from: label(pending.from), to: label(pending.to) })}
                  </p>
                  {fromInternet ? (
                    <>
                      <div className={styles.chips} role="radiogroup" aria-label={t("firewall.howLabel")}>
                        {PUBLISH.map((m) => (
                          <button
                            key={m}
                            type="button"
                            role="radio"
                            aria-checked={mode === m}
                            className={`${styles.chip} ${mode === m ? styles.chipOn : ""}`}
                            onClick={() => setMode(m)}
                          >
                            {t(`firewall.how.${m}`)}
                          </button>
                        ))}
                      </div>
                      <p className={styles.muted}>{t(`firewall.howNote.${mode}`, { to: label(pending.to), ext: EXT_PORT })}</p>
                    </>
                  ) : (
                    <label className={styles.fwPort}>
                      <span>{t("firewall.portLabel")}</span>
                      <input
                        value={port}
                        onChange={(e) => setPort(e.target.value.replace(/\D/g, "").slice(0, 5))}
                        inputMode="numeric"
                        placeholder={t("firewall.portPlaceholder")}
                        autoComplete="off"
                        data-act={pending.to === "db" ? "db" : undefined}
                      />
                    </label>
                  )}
                  <div className={styles.btnRow}>
                    <button type="submit" className={styles.btnSmall} disabled={!fromInternet && !port} data-act={submitAct}>
                      {fromInternet ? t("firewall.publish") : t("firewall.create")}
                    </button>
                    <button type="button" className={styles.btnSmallGhost} onClick={() => setPending(null)}>
                      {t("firewall.cancel")}
                    </button>
                  </div>
                </form>
              ) : (
                <div className={styles.fwBar}>
                  <p className={styles.hint} aria-live="polite">{hint}</p>
                </div>
              ))}

            {danger && <p className={styles.warn}>⚠ {t("firewall.danger")}</p>}
          </div>

          <div className={styles.ruleList}>
            <p className={styles.smallLabel}>{t("firewall.rules")}</p>
            {rules.length === 0 ? (
              <p className={styles.muted}>{t("firewall.noRules")}</p>
            ) : (
              <ul>
                {rules.map((r) => (
                  <li key={r.id} data-bad={r.from === "internet" && r.to === "db" ? true : undefined}>
                    <code>{ruleText(r)}</code>
                    <button type="button" onClick={() => setRules((prev) => prev.filter((x) => x.id !== r.id))}>
                      {t("firewall.remove")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
