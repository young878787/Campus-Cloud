import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import PixelSprite from "../PixelSprite";
import { ICONS, ICON_PALETTE } from "../icons";
import STATS from "../../stats.json";
import styles from "./Games.module.scss";
import s from "./Student.module.scss";
import { useEmit } from "./useEmit";

const SLOTS = ["wed", "thu", "fri"];
const PHASES = ["form", "sent", "approved", "waiting", "booting", "booted"];

/**
 * 學生篇：申請一台機器。選範本、選時段 → 送出（送出前已檢查時段容量）→ 管理員核准 → 倒數到時段開始 → 自動開機。
 * onEvent：submitted／approved／booted（章魚導覽用）。
 */
export default function RequestGame({ onEvent }) {
  const { t } = useTranslation("pixel");
  const emit = useEmit(onEvent);
  const templates = STATS.templates;
  const [tpl, setTpl] = useState(0);
  const [slot, setSlot] = useState("wed");
  const [phase, setPhase] = useState("form");
  const [count, setCount] = useState(3);
  const timers = useRef([]);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);
  const later = (ms, fn) => timers.current.push(window.setTimeout(fn, ms));

  const submit = () => {
    setPhase("sent");
    emit("submitted");
    // 節奏要夠慢：導覽的旁白跟著 approved／booted 換句，每一步都要留時間讓人讀完、看到步驟亮起
    later(3000, () => {
      setPhase("approved");
      emit("approved");
    });
    later(4800, () => {
      setPhase("waiting");
      setCount(3);
    });
    later(5800, () => setCount(2));
    later(6800, () => setCount(1));
    later(7800, () => setPhase("booting"));
    later(9300, () => {
      setPhase("booted");
      emit("booted");
    });
  };

  const at = (p) => PHASES.indexOf(phase) >= PHASES.indexOf(p);
  const steps = t("student.request.steps", { returnObjects: true });
  const stepDone = [at("sent"), at("approved"), at("booting"), at("booted")];
  const slotLabel = t(`student.request.slots.${slot}`);
  const status = {
    form: t("student.request.status.form"),
    sent: t("student.request.status.sent"),
    approved: t("student.request.status.approved", { slot: slotLabel }),
    waiting: t("student.request.status.waiting", { n: count }),
    booting: t("student.request.status.booting"),
    booted: t("student.request.status.booted", { vm: "vm-2481" }),
  }[phase];
  const locked = phase !== "form";

  return (
    <div className={styles.game}>
      <ol className={styles.steps}>
        {steps.map((step, i) => (
          <li key={step} className={stepDone[i] ? styles.stepDone : undefined}>
            <span>{i + 1}</span>
            {step}
          </li>
        ))}
      </ol>

      <div className={s.requestCols}>
        <div className={s.form}>
          <p className={styles.smallLabel}>{t("student.request.template")}</p>
          <div className={styles.chips} role="radiogroup" aria-label={t("student.request.template")}>
            {templates.map((item, i) => (
              <button
                key={item.name}
                type="button"
                role="radio"
                aria-checked={tpl === i}
                className={`${styles.chip} ${tpl === i ? styles.chipOn : ""}`}
                onClick={() => setTpl(i)}
                disabled={locked}
              >
                {item.name}
                <em>{item.kind}</em>
              </button>
            ))}
          </div>
          <p className={styles.smallLabel}>{t("student.request.slot")}</p>
          <div className={styles.chips} role="radiogroup" aria-label={t("student.request.slot")}>
            {SLOTS.map((id) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={slot === id}
                className={`${styles.chip} ${slot === id ? styles.chipOn : ""}`}
                onClick={() => setSlot(id)}
                disabled={locked}
              >
                {t(`student.request.slots.${id}`)}
              </button>
            ))}
          </div>
          <p className={styles.smallLabel}>{t("student.request.courseLabel")}</p>
          <span className={styles.chipStatic}>{t("student.request.course")}</span>
          <div className={styles.btnRow}>
            <button type="button" className={styles.btn} onClick={submit} disabled={locked} data-act="submitted">
              {t("student.request.submit")}
            </button>
          </div>
        </div>

        <div className={s.statusCard} data-phase={phase} aria-live="polite">
          <PixelSprite className={s.statusIcon} rows={ICONS.monitor} palette={ICON_PALETTE} cell={5} />
          <strong>{status}</strong>
          {at("approved") && (
            <small>
              {templates[tpl].name}・{slotLabel}
            </small>
          )}
        </div>
      </div>
    </div>
  );
}
