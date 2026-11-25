import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import STATS from "../../stats.json";
import styles from "./Games.module.scss";
import { useEmit } from "./useEmit";

const TOTAL = STATS.classroom?.seats ?? 40;
const STUCK = [6, 17, 29]; // 建置失敗的那幾台
const FAILS = [3, 14, 22, 35]; // AI 導師檢查沒通過的同學
const STAGGER_MS = 45;
const REVIEW_MS = 1200; // 等管理員班級審核（示意，實際由管理員在「班級審核」核准）
const seatId = (i) => `pc-${String(i + 1).padStart(2, "0")}`;
const seatCpu = (i) => 18 + ((i * 37) % 61);

/**
 * 第 5 關：整班上課，照實際系統的流程：
 *   建班精靈設好課表、名單與教學環境 → 按「送出建機」→ 管理員「班級審核」核准 → 全班機器一起建；
 *   有幾台沒建成功時，整班按「重試失敗項目」（會再送管理員審核），不能點單台重開；
 *   全部建好後，AI 導師檢查依檢查項目在每台機器上跑腳本，紅色是沒通過的同學，點一下看哪一項沒過。
 * 檢查完就過關。
 * preview：示意畫面，停在 AI 導師檢查完的樣子。
 */
export default function ClassroomGame({ onWin, onEvent, preview = false }) {
  const emit = useEmit(onEvent);
  const { t } = useTranslation("pixel");
  const { t: tl } = useTranslation("landing");
  const reasons = t("classroom.reasons", { returnObjects: true });
  const [seats, setSeats] = useState(() =>
    Array.from({ length: TOTAL }, (_, i) => (!preview ? "off" : FAILS.includes(i) ? "fail" : "pass")),
  );
  const [phase, setPhase] = useState(preview ? "checked" : "idle"); // idle | review | building | failed | retrying | ready | checking | checked
  const [picked, setPicked] = useState(null);
  const timers = useRef([]);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);
  const later = (ms, fn) => timers.current.push(window.setTimeout(fn, ms));
  const setSeat = (i, state) => setSeats((prev) => prev.map((s, j) => (j === i ? state : s)));

  const build = () => {
    setPhase("review");
    setPicked(null);
    setSeats(Array(TOTAL).fill("off"));
    later(REVIEW_MS, () => {
      setPhase("building");
      for (let i = 0; i < TOTAL; i += 1) later(i * STAGGER_MS, () => setSeat(i, STUCK.includes(i) ? "stuck" : "on"));
      later(TOTAL * STAGGER_MS + 200, () => {
        setPhase("failed");
        emit("built");
      });
    });
  };

  /* 重試失敗項目：整班一次，失敗的那幾台重新送審、重建 */
  const retry = () => {
    setPhase("retrying");
    setSeats((prev) => prev.map((s) => (s === "stuck" ? "restarting" : s)));
    later(REVIEW_MS + 600, () => {
      setSeats((prev) => prev.map((s) => (s === "restarting" ? "on" : s)));
      setPhase("ready");
      emit("fixed");
    });
  };

  const check = () => {
    setPhase("checking");
    for (let i = 0; i < TOTAL; i += 1) later(i * STAGGER_MS, () => setSeat(i, FAILS.includes(i) ? "fail" : "pass"));
    later(TOTAL * STAGGER_MS + 200, () => {
      setPhase("checked");
      onWin?.();
      emit("checked");
    });
  };

  const online = seats.filter((s) => s !== "off" && s !== "stuck" && s !== "restarting").length;
  const stuckLeft = seats.filter((s) => s === "stuck").length;

  let status = tl("classroom.online", { online, seats: TOTAL });
  if (phase === "review") status = t("classroom.review");
  if (phase === "building") status = t("classroom.building", { n: online, total: TOTAL });
  if (phase === "failed") status = t("classroom.stuck", { n: stuckLeft });
  if (phase === "retrying") status = t("classroom.retrying");
  if (phase === "ready") status = t("classroom.allUp", { n: TOTAL });
  if (phase === "checking") status = t("classroom.checking");
  if (phase === "checked") {
    // 示意畫面不能點，不提「點紅色座位看原因」
    status = t(preview ? "classroom.resultShort" : "classroom.result", { pass: TOTAL - FAILS.length, fail: FAILS.length });
  }

  return (
    <div className={styles.game}>
      <div className={styles.classHead}>
        <p className={styles.classStatus} data-phase={phase} aria-live="polite">{status}</p>
      </div>

      <div className={styles.seatGrid} style={{ "--cols": 10 }}>
        {seats.map((state, i) => {
          const clickable = state === "fail";
          return (
            <button
              key={i}
              type="button"
              className={styles.seat}
              data-state={state}
              data-act={state === "fail" ? "picked" : undefined}
              disabled={!clickable}
              title={state === "off" ? seatId(i) : t("classroom.seat", { id: seatId(i), cpu: seatCpu(i) })}
              aria-label={seatId(i)}
              onClick={() => {
                setPicked(i);
                emit("picked");
              }}
            >
              <i />
            </button>
          );
        })}
      </div>

      {picked !== null && seats[picked] === "fail" && (
        <p className={styles.note}>
          {seatId(picked)}：{reasons[FAILS.indexOf(picked) % reasons.length]}
        </p>
      )}

      <div className={styles.btnRow}>
        {(phase === "idle" || phase === "review" || phase === "building") && (
          <button type="button" className={styles.btn} onClick={build} disabled={phase !== "idle"} data-act="built">
            {t("classroom.build", { n: TOTAL })}
          </button>
        )}
        {(phase === "failed" || phase === "retrying") && (
          <button type="button" className={styles.btn} onClick={retry} disabled={phase === "retrying"} data-act="fixed">
            {t("classroom.retry")}
          </button>
        )}
        {(phase === "ready" || phase === "checking") && (
          <button type="button" className={styles.btn} onClick={check} disabled={phase !== "ready"} data-act="checked">
            ✦ {t("classroom.check")}
          </button>
        )}
        {phase === "checked" && (
          <button type="button" className={styles.btnGhost} onClick={build}>
            {t("try.restart")}
          </button>
        )}
      </div>
    </div>
  );
}
