import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./Games.module.scss";
import s from "./Student.module.scss";
import { useEmit } from "./useEmit";

const PROMPT = "student@vm-2481:~$";
const FILES = "lab-03.py  notes.md  report.md";

/**
 * 學生篇：先存檔再亂改。建立快照 → 手滑刪掉作業資料夾 → 還原快照，作業回來了。
 * 刪除要先有快照才按得下去（故事一定救得回來）；全部只在前端演，不連任何機器。
 * onEvent：snapshot／broke／restored（章魚導覽用）。
 */
export default function SnapshotGame({ onEvent }) {
  const { t } = useTranslation("pixel");
  const emit = useEmit(onEvent);
  const [snaps, setSnaps] = useState([]);
  const [broken, setBroken] = useState(false);
  const [lines, setLines] = useState([
    { kind: "cmd", text: "ls homework/" },
    { kind: "out", text: FILES },
  ]);

  const take = () => {
    const name = `snap-${String(snaps.length + 1).padStart(2, "0")}`;
    setSnaps((prev) => [...prev, name]);
    emit("snapshot");
  };
  const breakIt = () => {
    setBroken(true);
    setLines((prev) =>
      [
        ...prev,
        { kind: "cmd", text: "rm -rf homework/" },
        { kind: "cmd", text: "ls homework/" },
        { kind: "err", text: t("student.snapshot.missing") },
      ].slice(-8),
    );
    emit("broke");
  };
  const restore = () => {
    const name = snaps[snaps.length - 1];
    setBroken(false);
    setLines((prev) =>
      [
        ...prev,
        { kind: "note", text: t("student.snapshot.restoredLog", { name }) },
        { kind: "cmd", text: "ls homework/" },
        { kind: "out", text: FILES },
      ].slice(-8),
    );
    emit("restored");
  };

  return (
    <div className={styles.game}>
      <div className={s.snapCols}>
        <div className={`${styles.term} ${s.snapTerm}`} data-broken={broken || undefined}>
          <div className={styles.termBody}>
            {lines.map((line, i) =>
              line.kind === "cmd" ? (
                <p key={i}>
                  <span className={styles.termPrompt}>{PROMPT}</span> {line.text}
                </p>
              ) : (
                <p key={i} className={line.kind === "err" ? styles.termErr : line.kind === "note" ? s.termNote : undefined}>
                  {line.text}
                </p>
              ),
            )}
          </div>
        </div>

        <div className={s.snapSide}>
          <p className={styles.smallLabel}>{t("student.snapshot.snaps")}</p>
          {snaps.length === 0 ? (
            <p className={styles.muted}>{t("student.snapshot.none")}</p>
          ) : (
            <ul className={s.snapList}>
              {snaps.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          )}
          <div className={s.snapActions}>
            <button type="button" className={styles.btn} onClick={take} disabled={broken} data-act="snapshot">
              {t("student.snapshot.take")}
            </button>
            <button
              type="button"
              className={`${styles.btnGhost} ${s.danger}`}
              onClick={breakIt}
              disabled={broken || snaps.length === 0}
              data-act="broke"
            >
              {t("student.snapshot.break")}
            </button>
            <button
              type="button"
              className={styles.btnGhost}
              onClick={restore}
              disabled={!broken}
              data-act="restored"
            >
              {t("student.snapshot.restore")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
