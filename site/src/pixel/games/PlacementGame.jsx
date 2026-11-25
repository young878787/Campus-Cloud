import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import PixelSprite from "../PixelSprite";
import { ICONS, ICON_PALETTE } from "../icons";
import styles from "./Games.module.scss";
import { useEmit } from "./useEmit";

const START = [
  { node: "pve-01", load: 35, gpu: false },
  { node: "pve-02", load: 58, gpu: false },
  { node: "pve-03", load: 70, gpu: true },
];
/* 各課程的需求：吃多少負載、要不要 GPU */
const COURSES = {
  python: { demand: 8, gpu: false },
  web: { demand: 4, gpu: false },
  ml: { demand: 20, gpu: true },
};
const SEGMENTS = 10;

function scoreOf(node, course) {
  if (!course) return null;
  const need = COURSES[course];
  if (need.gpu && !node.gpu) return { score: 0, reason: "noGpu" };
  if (node.load + need.demand > 100) return { score: 0, reason: "full" };
  return { score: Math.round(100 - node.load - need.demand / 2) };
}

/* AI 建議一個字一個字打出來 */
function useTypewriter(text, instant = false) {
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
    if (!text) return undefined;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || instant) {
      setN(text.length);
      return undefined;
    }
    const id = window.setInterval(() => setN((v) => (v >= text.length ? v : v + 1)), 28);
    return () => window.clearInterval(id);
  }, [text, instant]);
  return text.slice(0, n);
}

/**
 * 第 2 關：AI 助手＋排程，照實際系統分成兩件事：
 *   AI 助手：跟它說需求（選一句），推薦範本與規格、幫你填好申請單（實際是右下角的 AI 助手）；
 *   放哪一台不是 AI：核准時由排程依各主機的 CPU、記憶體、磁碟與負載評分挑最空的那台。
 * 按「模擬變忙」讓某台主機負載升高（示範用，實際沒有這個按鈕），看下一次會改放別台就過關。
 * preview：示意畫面，已選好「Python 程式入門」、標出會放的主機。
 */
export default function PlacementGame({ onWin, onEvent, preview = false }) {
  const emit = useEmit(onEvent);
  const { t } = useTranslation("pixel");
  const [course, setCourse] = useState(preview ? "python" : null);
  const [nodes, setNodes] = useState(START);
  const won = useRef(false);
  const firstBest = useRef(null);

  const scored = nodes.map((n) => ({ ...n, result: scoreOf(n, course) }));
  const best = course
    ? scored.reduce((a, b) => ((b.result?.score ?? 0) > (a.result?.score ?? 0) ? b : a))
    : null;
  const bestNode = best && best.result.score > 0 ? best.node : null;
  const typed = useTypewriter(course ? t(`placement.courses.${course}.rec`) : "", preview);

  useEffect(() => {
    if (!bestNode) return;
    if (firstBest.current === null) firstBest.current = bestNode;
    else if (firstBest.current !== bestNode && !won.current) {
      won.current = true;
      onWin?.();
      emit("moved");
    }
  }, [bestNode, onWin]);

  const pick = (id) => {
    setCourse(id);
    firstBest.current = null;
    emit("course", id);
  };
  const addLoad = (node) =>
    setNodes((prev) => prev.map((n) => (n.node === node ? { ...n, load: Math.min(100, n.load + 15) } : n)));

  return (
    <div className={styles.game}>
      <div className={styles.chips} role="radiogroup" aria-label={t("placement.pick")}>
        {Object.keys(COURSES).map((id) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={course === id}
            data-act="course"
            className={`${styles.chip} ${course === id ? styles.chipOn : ""}`}
            onClick={() => pick(id)}
          >
            {t(`placement.courses.${id}.name`)}
          </button>
        ))}
      </div>

      <div className={styles.aiCard} data-empty={!course || undefined}>
        <PixelSprite rows={ICONS.sparkle} palette={ICON_PALETTE} cell={3} />
        <div>
          <p className={styles.smallLabel}>{t("placement.ai")}</p>
          <p className={styles.aiText}>
            {course ? typed : t("placement.pick")}
            {course && typed.length < t(`placement.courses.${course}.rec`).length && <i className={styles.caret} />}
          </p>
          {course && typed.length === t(`placement.courses.${course}.rec`).length && (
            <p className={styles.aiPlaced}>✓ {t("placement.filled")}</p>
          )}
        </div>
      </div>

      {/* 放哪一台：核准時排程依負載評分決定（不是 AI） */}
      <p className={styles.smallLabel}>{t("placement.scheduler")}</p>

      <div className={styles.nodes}>
        {scored.map((n) => {
          const isBest = n.node === bestNode;
          const filled = Math.round((n.load / 100) * SEGMENTS);
          return (
            <div key={n.node} className={`${styles.nodeCard} ${isBest ? styles.nodeBest : ""}`}>
              {isBest && (
                <span key={`${course}-${bestNode}`} className={styles.dropVm} aria-hidden="true">
                  <PixelSprite rows={ICONS.monitor} palette={ICON_PALETTE} cell={2} />
                </span>
              )}
              <PixelSprite rows={ICONS.server} palette={ICON_PALETTE} cell={4} />
              <strong>
                {n.node}
                {n.gpu && <em className={styles.gpuTag}>GPU</em>}
              </strong>
              <span className={styles.capBar} data-level={n.load >= 85 ? "high" : n.load >= 60 ? "mid" : "low"}>
                {Array.from({ length: SEGMENTS }, (_, i) => <i key={i} className={i < filled ? styles.barOn : undefined} />)}
              </span>
              <small>{t("placement.load", { n: n.load })}</small>
              <span className={styles.score}>
                {n.result == null ? "—" : n.result.reason ? t(`placement.${n.result.reason}`) : n.result.score}
              </span>
              <button
                type="button"
                className={styles.btnSmallGhost}
                onClick={() => addLoad(n.node)}
                disabled={n.load >= 100}
                data-act={isBest ? "moved" : undefined}
              >
                ＋ {t("placement.addLoad")}
              </button>
            </div>
          );
        })}
      </div>

      <div className={styles.btnRow}>
        {bestNode && <p className={styles.aiPlaced}>→ {t("placement.placed", { node: bestNode, score: best.result.score })}</p>}
        <button type="button" className={styles.chipQuiet} onClick={() => setNodes(START)}>
          {t("placement.clear")}
        </button>
      </div>
    </div>
  );
}
