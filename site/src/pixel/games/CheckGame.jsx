import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./Games.module.scss";
import s from "./Student.module.scss";
import { useEmit } from "./useEmit";

const ITEMS = ["service", "port", "page"];
const STEP_MS = 550;

/**
 * 學生篇：老師發布這週的檢查項目後，學生自己送出 AI 導師檢查。第一次「首頁顯示作業標題」沒過、寫出原因；
 * 按「改好首頁」修好（學生在自己機器裡能改的東西；課堂機的防火牆學生不能改），再檢查一次就全部通過。
 * onEvent：checked（第一次檢查完）／fixed／passed（全部通過）（章魚導覽用）。
 */
export default function CheckGame({ onEvent }) {
  const { t } = useTranslation("pixel");
  const emit = useEmit(onEvent);
  const [fixed, setFixed] = useState(false);
  const [results, setResults] = useState({}); // id → "checking" | "ok" | "fail"
  const [running, setRunning] = useState(false);
  const [rounds, setRounds] = useState(0);
  const timers = useRef([]);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  const run = () => {
    setRunning(true);
    setResults({});
    const pageOk = fixed;
    ITEMS.forEach((id, i) => {
      timers.current.push(
        window.setTimeout(() => setResults((prev) => ({ ...prev, [id]: "checking" })), i * STEP_MS),
        window.setTimeout(
          () => setResults((prev) => ({ ...prev, [id]: id === "page" && !pageOk ? "fail" : "ok" })),
          (i + 1) * STEP_MS,
        ),
      );
    });
    timers.current.push(
      window.setTimeout(() => {
        setRunning(false);
        setRounds((n) => n + 1);
        emit("checked");
        if (pageOk) emit("passed");
      }, ITEMS.length * STEP_MS + 100),
    );
  };

  const fix = () => {
    setFixed(true);
    setResults((prev) => ({ ...prev, page: undefined }));
    emit("fixed");
  };

  const okCount = ITEMS.filter((id) => results[id] === "ok").length;
  const done = rounds > 0 && !running;

  return (
    <div className={styles.game}>
      <p className={styles.smallLabel}>{t("student.check.assignment")}</p>
      <ul className={`${styles.goals} ${s.checkList}`}>
        {ITEMS.map((id, i) => {
          const state = results[id];
          return (
            <li key={id} data-state={state} className={state === "ok" ? styles.goalOk : undefined}>
              <span aria-hidden="true">{state === "ok" ? "✓" : state === "fail" ? "✗" : state === "checking" ? "…" : i + 1}</span>
              <div>
                {t(`student.check.items.${id}`)}
                {state === "fail" && (
                  <p className={s.failWhy}>
                    {t("student.check.failPage")}
                    <button type="button" className={styles.btnSmall} onClick={fix} data-act="fixed">
                      {t("student.check.fix")}
                    </button>
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <div className={styles.btnRow}>
        <button type="button" className={styles.btn} onClick={run} disabled={running} data-act="checked passed">
          {running ? t("student.check.checking") : rounds > 0 ? t("student.check.rerun") : t("student.check.run")}
        </button>
        {done && (
          <span className={okCount === ITEMS.length ? s.allPass : styles.muted} aria-live="polite">
            {okCount === ITEMS.length
              ? t("student.check.allPass")
              : t("student.check.result", { ok: okCount, total: ITEMS.length })}
          </span>
        )}
      </div>
    </div>
  );
}
