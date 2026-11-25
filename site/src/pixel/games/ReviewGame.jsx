import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import PixelSprite from "../PixelSprite";
import { ICONS, ICON_PALETTE } from "../icons";
import STATS from "../../stats.json";
import styles from "./Games.module.scss";
import { useEmit } from "./useEmit";

/* 申請池：依序出現；load 是佔這個時段容量的百分比 */
const POOL = [
  { cpu: 2, ram: 4, load: 12 },
  { cpu: 2, ram: 8, load: 18 },
  { cpu: 4, ram: 8, load: 25 },
  { cpu: 1, ram: 2, load: 6 },
  { cpu: 4, ram: 16, load: 30 },
];
const SEGMENTS = 20;

/**
 * 第 4 關：你是管理員（申請審核只有管理員能做）。核准 → 時間到自動建好、開機。
 * 容量在學生送出申請時就先算：這個時段放不下的申請送不出去，月曆推薦還有空的時段讓學生改選
 * （不會自動改排）。待審核的申請也算在容量裡。
 * 看過「自動開機」與「改選推薦時段」兩種結果就過關。
 * preview：示意畫面，第一筆已核准開機、還有兩筆待審核。
 */
export default function ReviewGame({ onWin, onEvent, preview = false }) {
  const emit = useEmit(onEvent);
  const { t } = useTranslation("pixel");
  const students = t("review.students", { returnObjects: true });
  const courses = t("review.courses", { returnObjects: true });
  const base = STATS.capacity?.usedPercent ?? 62;
  const [used, setUsed] = useState(preview ? base + POOL[0].load : base);
  const [nextNo, setNextNo] = useState(preview ? 3 : 2);
  const [queue, setQueue] = useState(() => (preview ? [1, 2] : [0, 1]).map((i) => makeRequest(i)));
  const [blocked, setBlocked] = useState(null); // 送不出去的那筆申請（時段放不下）
  const [done, setDone] = useState(() => (preview ? [{ ...makeRequest(0), status: "booted" }] : [])); // { ...req, status }
  const [note, setNote] = useState("");
  const won = useRef(false);
  const timers = useRef([]);

  function makeRequest(i) {
    return {
      id: i,
      who: students[i % students.length],
      course: courses[i % courses.length],
      ...POOL[i % POOL.length],
    };
  }

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  useEffect(() => {
    if (won.current) return;
    const booted = done.some((r) => r.status === "booted");
    const moved = done.some((r) => r.slot) || queue.some((r) => r.slot);
    if (booted && moved) {
      won.current = true;
      onWin?.();
    }
  }, [done, queue, onWin]);

  const setStatus = (id, status) =>
    setDone((prev) => prev.map((r) => (r.id === id ? { ...r, status } : r)));

  const approve = (req) => {
    setQueue((prev) => prev.filter((r) => r.id !== req.id));
    setNote("");
    emit("approved");
    // 改選到別的時段的申請：不佔這個時段，排在那個時段開機
    if (req.slot) {
      setDone((prev) => [{ ...req, status: "later" }, ...prev]);
      return;
    }
    setUsed((u) => u + req.load);
    setDone((prev) => [{ ...req, status: "scheduled" }, ...prev]);
    timers.current.push(
      window.setTimeout(() => setStatus(req.id, "booting"), 1100),
      window.setTimeout(() => {
        setStatus(req.id, "booted");
        emit("booted");
      }, 2300),
    );
  };

  const reject = (req) => {
    setQueue((prev) => prev.filter((r) => r.id !== req.id));
    setNote(t("review.rejected"));
  };

  /* 學生再送一筆：已核准的＋待審核的＋這一筆超過 100% 就送不出去，改推薦別的時段 */
  const pendingLoad = queue.filter((r) => !r.slot).reduce((sum, r) => sum + r.load, 0);
  const more = () => {
    const req = makeRequest(nextNo);
    setNextNo((n) => n + 1);
    setNote("");
    if (used + pendingLoad + req.load > 100) {
      setBlocked(req);
      return;
    }
    setQueue((prev) => [...prev, req].slice(-4));
  };
  const takeAlt = () => {
    setQueue((prev) => [...prev, { ...blocked, slot: t("review.altSlot") }].slice(-4));
    setBlocked(null);
    emit("moved");
  };

  const filled = Math.min(SEGMENTS, Math.round((used / 100) * SEGMENTS));
  const booted = done.filter((r) => r.status === "booted").length;

  return (
    <div className={styles.game}>
      <div className={styles.capacity}>
        <span className={styles.smallLabel}>{t("review.capacity")}</span>
        <span className={styles.capBar} data-level={used >= 85 ? "high" : used >= 70 ? "mid" : "low"}>
          {Array.from({ length: SEGMENTS }, (_, i) => <i key={i} className={i < filled ? styles.barOn : undefined} />)}
        </span>
        <strong>{used}%</strong>
      </div>

      <div className={styles.reviewCols}>
        <section className={styles.reviewCol}>
          <h4>
            <PixelSprite rows={ICONS.calendar} palette={ICON_PALETTE} cell={2} />
            {t("review.queue")}
            <em>{queue.length}</em>
          </h4>
          {queue.length === 0 && <p className={styles.muted}>{t("review.empty")}</p>}
          {queue.map((req) => (
            <article key={req.id} className={styles.reqCard}>
              <div>
                <strong>{req.who}</strong>
                <span>{req.course}</span>
                <small>{req.slot ? t("review.inSlot", { slot: req.slot }) : t("review.spec", req)}</small>
              </div>
              <div className={styles.reqActions}>
                <button type="button" className={styles.btnSmall} onClick={() => approve(req)} data-act="approved">
                  {t("review.approve")}
                </button>
                <button type="button" className={styles.btnSmallGhost} onClick={() => reject(req)}>
                  {t("review.reject")}
                </button>
              </div>
            </article>
          ))}
          {note && <p className={styles.note}>{note}</p>}
          {/* 學生那邊：送出時就檢查容量，放不下會被擋、月曆推薦別的時段 */}
          {blocked ? (
            <div className={styles.blockedCard}>
              <p>{t("review.blocked", { who: blocked.who })}</p>
              <button type="button" className={styles.btnSmall} onClick={takeAlt} data-act="moved">
                {t("review.takeAlt", { slot: t("review.altSlot") })}
              </button>
            </div>
          ) : (
            <button type="button" className={styles.btnGhost} onClick={more} data-act="moved">
              ＋ {t("review.more")}
            </button>
          )}
        </section>

        <span className={styles.flowArrow} aria-hidden="true">
          <i />
          <i />
          <i />
        </span>

        <section className={styles.reviewCol}>
          <h4>
            <PixelSprite rows={ICONS.server} palette={ICON_PALETTE} cell={2} />
            {t("review.provisioned")}
          </h4>
          {done.length === 0 && <p className={styles.muted}>{t("review.noneYet")}</p>}
          {done.slice(0, 4).map((req) => (
            <article key={req.id} className={styles.provCard} data-status={req.status}>
              <strong>{req.who}</strong>
              <span>
                {req.status === "scheduled" && t("review.scheduled")}
                {req.status === "booting" && t("review.booting")}
                {req.status === "booted" && `✓ ${t("review.booted")}`}
                {req.status === "later" && t("review.later", { slot: req.slot })}
              </span>
            </article>
          ))}
        </section>
      </div>

      <p className={styles.stat}>{t("review.stats", { done: done.length, booted })}</p>
    </div>
  );
}
