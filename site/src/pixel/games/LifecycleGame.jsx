import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import PixelSprite from "../PixelSprite";
import { ICONS, ICON_PALETTE } from "../icons";
import STATS from "../../stats.json";
import styles from "./Games.module.scss";
import { useEmit } from "./useEmit";

const SPECS = [
  { cpu: 2, ram: 4 },
  { cpu: 4, ram: 8 },
  { cpu: 8, ram: 16 },
];
const BUILD_MS = 1600;
const REVIEW_MS = 1200; // 規格申請等管理員核准（示意，實際由管理員在「申請審核」按）
const REBOOT_MS = 1400; // 套用新規格：關機、改規格、開機
const EXPIRE_STEP_MS = 800;

/**
 * 第 1 關：一台機器的一生，照實際系統的流程：
 *   建立：老師／管理員用立即模式直接建（學生是送申請，管理員核准後時間到自動建，見申請審核那章）；
 *   快照：資源詳情的「快照」分頁按「建立快照」；
 *   調整規格：送出申請 → 管理員核准 → 自己按「套用新規格」（關機、改規格、開機），不用重灌；
 *   到期回收：不是按鈕，是排程自動做——到期前寄信、到期關機、寬限 7 天後回收（這裡用「快轉到到期日」示範）。
 * 四個步驟都做過就過關；上方的步驟列跟著亮。
 * preview：示意畫面，停在「建好、快照過、加過規格」的樣子。
 * onEvent：created／snapshot／resized／recycled（章魚導覽用）。
 */
export default function LifecycleGame({ onWin, onEvent, preview = false }) {
  const emit = useEmit(onEvent);
  const { t } = useTranslation("pixel");
  const { t: tl } = useTranslation("landing");
  const steps = tl("lifecycle.steps", { returnObjects: true });
  const templates = STATS.templates;
  const [tpl, setTpl] = useState(templates[0].name);
  const [phase, setPhase] = useState(preview ? "running" : "empty"); // empty | building | running | expiring
  const [power, setPower] = useState("on"); // on | rebooting | off
  const [resize, setResize] = useState("idle"); // idle | pending | approved
  const [spec, setSpec] = useState(preview ? 1 : 0);
  const [snaps, setSnaps] = useState(preview ? ["snap-01"] : []);
  const [log, setLog] = useState(() =>
    preview
      ? [
          t("lifecycle.log.resized", SPECS[1]),
          t("lifecycle.log.snap", { name: "snap-01" }),
          t("lifecycle.log.created", { tpl: templates[0].name, vm: "vm-2481", ...SPECS[0] }),
        ]
      : [],
  );
  const [done, setDone] = useState(() => new Set(preview ? [0, 1, 2] : []));
  const [vmNo, setVmNo] = useState(2481);
  const timers = useRef([]);
  const vm = `vm-${vmNo}`;

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);
  const later = (ms, fn) => timers.current.push(window.setTimeout(fn, ms));

  const mark = (step) =>
    setDone((prev) => {
      const next = new Set(prev).add(step);
      if (next.size === 4 && prev.size < 4) onWin?.();
      return next;
    });
  const push = (line) => setLog((prev) => [line, ...prev].slice(0, 4));

  const create = () => {
    setPhase("building");
    setPower("on");
    setResize("idle");
    setSpec(0);
    setSnaps([]);
    later(BUILD_MS, () => {
      setPhase("running");
      push(t("lifecycle.log.created", { tpl, vm, ...SPECS[0] }));
      mark(0);
      emit("created");
    });
  };
  const snapshot = () => {
    const name = `snap-${String(snaps.length + 1).padStart(2, "0")}`;
    setSnaps((prev) => [...prev, name].slice(-4));
    push(t("lifecycle.log.snap", { name }));
    mark(1);
    emit("snapshot");
  };
  const next = SPECS[(spec + 1) % SPECS.length];
  const askResize = () => {
    setResize("pending");
    push(t("lifecycle.log.asked", next));
    later(REVIEW_MS, () => {
      setResize("approved");
      push(t("lifecycle.log.approved"));
    });
  };
  const applyResize = () => {
    setResize("idle");
    setPower("rebooting");
    later(REBOOT_MS, () => {
      setSpec((s) => (s + 1) % SPECS.length);
      setPower("on");
      push(t("lifecycle.log.resized", next));
      mark(2);
      emit("resized");
    });
  };
  const fastForward = () => {
    setPhase("expiring");
    setResize("idle");
    push(t("lifecycle.log.mail", { vm }));
    later(EXPIRE_STEP_MS, () => {
      setPower("off");
      push(t("lifecycle.log.off", { vm }));
    });
    later(EXPIRE_STEP_MS * 2, () => {
      push(t("lifecycle.log.recycled", { vm }));
      mark(3);
      emit("recycled");
      setPhase("empty");
      setPower("on");
      setVmNo((n) => n + 1);
    });
  };

  const running = phase === "running" && power === "on";
  const { cpu, ram } = SPECS[spec];
  let pill = <span className={styles.pillOk}>{t("lifecycle.running")}</span>;
  if (power === "rebooting") pill = <span className={styles.pillWait}>{t("lifecycle.rebooting")}</span>;
  if (power === "off") pill = <span className={styles.pillOff}>{t("lifecycle.off")}</span>;

  return (
    <div className={styles.game}>
      <ol className={styles.steps}>
        {steps.map((step, i) => (
          <li key={step} className={done.has(i) ? styles.stepDone : undefined}>
            <span>{i + 1}</span>
            {step}
          </li>
        ))}
      </ol>

      <div className={styles.lifecycle}>
        <div className={styles.lcControls}>
          <p className={styles.smallLabel}>{tl("lifecycle.templates")}</p>
          <div className={styles.chips} role="radiogroup" aria-label={tl("lifecycle.templates")}>
            {templates.map((item) => (
              <button
                key={item.name}
                type="button"
                role="radio"
                aria-checked={tpl === item.name}
                className={`${styles.chip} ${tpl === item.name ? styles.chipOn : ""}`}
                onClick={() => setTpl(item.name)}
                disabled={phase !== "empty"}
              >
                {item.name}
                <em>{item.kind}</em>
              </button>
            ))}
          </div>
          <div className={styles.btnRow}>
            {phase === "empty" || phase === "building" ? (
              <button type="button" className={styles.btn} onClick={create} disabled={phase === "building"} data-act="created">
                {phase === "building" ? t("lifecycle.building") : t("lifecycle.create")}
              </button>
            ) : (
              <>
                <button type="button" className={styles.btnGhost} onClick={snapshot} disabled={!running} data-act="snapshot">
                  {t("lifecycle.snapshot")}
                </button>
                {resize === "approved" ? (
                  <button type="button" className={styles.btn} onClick={applyResize} disabled={!running} data-act="resized">
                    {t("lifecycle.apply")}
                  </button>
                ) : (
                  <button
                    type="button"
                    className={styles.btnGhost}
                    onClick={askResize}
                    disabled={!running || resize === "pending"}
                    data-act="resized"
                  >
                    {resize === "pending" ? t("lifecycle.pending") : t("lifecycle.resize")}
                  </button>
                )}
                <button type="button" className={styles.btnGhost} onClick={fastForward} disabled={!running} data-act="recycled">
                  {phase === "expiring" ? t("lifecycle.expiring") : t("lifecycle.recycle")}
                </button>
              </>
            )}
          </div>
          {phase === "empty" && <p className={styles.muted}>{t("lifecycle.createNote")}</p>}
        </div>

        <div className={styles.lcMachine} data-phase={phase}>
          {phase === "empty" ? (
            <p className={styles.muted}>{t("lifecycle.empty")}</p>
          ) : (
            <>
              <PixelSprite className={styles.lcSprite} rows={ICONS.monitor} palette={ICON_PALETTE} />
              <strong className={styles.lcName}>{vm}</strong>
              <span className={styles.lcTpl}>{tpl}</span>
              {phase === "building" ? (
                <span className={styles.progress} aria-label={t("lifecycle.building")}>
                  {Array.from({ length: 10 }, (_, i) => (
                    <i key={i} style={{ animationDelay: `${i * (BUILD_MS / 10)}ms` }} />
                  ))}
                </span>
              ) : (
                pill
              )}
              <div className={styles.specBars}>
                <span>vCPU</span>
                <span className={styles.bar}>
                  {Array.from({ length: 8 }, (_, i) => <i key={i} className={i < cpu ? styles.barOn : undefined} />)}
                </span>
                <b>{cpu}</b>
                <span>RAM</span>
                <span className={styles.bar}>
                  {Array.from({ length: 8 }, (_, i) => <i key={i} className={i < ram / 2 ? styles.barOn : undefined} />)}
                </span>
                <b>{ram} GB</b>
              </div>
              {snaps.length > 0 && (
                <div className={styles.snapRow}>
                  <PixelSprite rows={ICONS.camera} palette={ICON_PALETTE} cell={2} />
                  {snaps.map((s) => <span key={s} className={styles.snapTag}>{s}</span>)}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <ul className={styles.log} aria-live="polite">
        {log.length === 0 && <li className={styles.logIdle}>{t("lifecycle.logIdle")}</li>}
        {log.map((line, i) => <li key={`${line}-${i}`}>{line}</li>)}
      </ul>
    </div>
  );
}
