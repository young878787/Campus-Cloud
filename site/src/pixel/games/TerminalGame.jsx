import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./Games.module.scss";
import { useEmit } from "./useEmit";

const HOST = "ct-2481";
const PROMPT = `root@${HOST}:~#`;
const HINTS = ["whoami", "ls", "uname -a", "hostname"];
const WIN_AFTER = 3;

/**
 * 第 6 關：打開就是真的機器。照實際系統：LXC 容器在瀏覽器開「終端機」（登入帳號是 root），
 * VM 則是「控制台」（VNC 桌面）。這裡是假的容器終端機，可以打幾個指令（或點提示）；
 * 成功跑過三種指令就過關。只在前端回應，不連任何機器。
 * preview：示意畫面，已經打過 whoami 與 ls。
 */
export default function TerminalGame({ onWin, onEvent, preview = false }) {
  const emit = useEmit(onEvent);
  const { t } = useTranslation("pixel");
  const [lines, setLines] = useState(() => [
    { kind: "out", text: `Debian GNU/Linux 13 ${HOST} tty1` },
    { kind: "out", text: t("terminal.welcome") },
    ...(preview
      ? [
          { kind: "cmd", text: "whoami" },
          { kind: "out", text: "root" },
          { kind: "cmd", text: "ls" },
          { kind: "out", text: "homework/  lab-03.py  notes.md  README.txt" },
        ]
      : []),
  ]);
  const [input, setInput] = useState("");
  const [used, setUsed] = useState(() => new Set());
  const bodyRef = useRef(null);
  const inputRef = useRef(null);
  const won = useRef(false);

  useEffect(() => {
    const body = bodyRef.current;
    if (body) body.scrollTop = body.scrollHeight;
  }, [lines]);

  const respond = (cmd) => {
    switch (cmd) {
      case "help":
        return [t("terminal.help")];
      case "whoami":
        return ["root"];
      case "ls":
        return ["homework/  lab-03.py  notes.md  README.txt"];
      case "uname -a":
        // 容器跟主機共用核心，所以是 PVE 的核心
        return [`Linux ${HOST} 6.8.12-4-pve #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux`];
      case "hostname":
        return [HOST];
      case "cat README.txt":
        return ["Put your homework in ~/homework."];
      default:
        return null;
    }
  };

  const run = (raw) => {
    const cmd = raw.trim().replace(/\s+/g, " ");
    setInput("");
    if (!cmd) {
      setLines((prev) => [...prev, { kind: "cmd", text: "" }]);
      return;
    }
    if (cmd === "clear") {
      setLines([]);
      return;
    }
    const out = respond(cmd);
    setLines((prev) =>
      [
        ...prev,
        { kind: "cmd", text: cmd },
        ...(out ?? [t("terminal.notFound", { cmd })]).map((text) => ({ kind: out ? "out" : "err", text })),
      ].slice(-40),
    );
    if (out) emit("cmd", cmd);
    if (out && cmd !== "help") {
      setUsed((prev) => {
        const next = new Set(prev).add(cmd);
        if (next.size >= WIN_AFTER && !won.current) {
          won.current = true;
          onWin?.();
        }
        return next;
      });
    }
  };

  return (
    <div className={styles.game}>
      {/* 點終端機任何地方都聚焦到輸入列（像真的終端機） */}
      <div className={styles.term} onClick={() => inputRef.current?.focus()}>
        <div className={styles.termBar} aria-hidden="true">
          <span />
          <span />
          <span />
          <b>{t("terminal.title", { host: HOST })}</b>
        </div>
        <div className={styles.termBody} ref={bodyRef} aria-live="polite">
          {lines.map((line, i) =>
            line.kind === "cmd" ? (
              <p key={i}>
                <span className={styles.termPrompt}>{PROMPT}</span> {line.text}
              </p>
            ) : (
              <p key={i} className={line.kind === "err" ? styles.termErr : undefined}>{line.text}</p>
            ),
          )}
          <form
            className={styles.termInput}
            onSubmit={(e) => {
              e.preventDefault();
              run(input);
            }}
          >
            <label>
              <span className={styles.termPrompt}>{PROMPT}</span>
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t("terminal.placeholder")}
                aria-label={t("terminal.placeholder")}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck="false"
              />
            </label>
          </form>
        </div>
      </div>
      <div className={styles.chips}>
        <span className={styles.smallLabel}>{t("terminal.try")}</span>
        {HINTS.map((cmd) => (
          <button
            key={cmd}
            type="button"
            className={`${styles.chip} ${used.has(cmd) ? styles.chipDone : ""}`}
            onClick={() => run(cmd)}
            data-act={`cmd:${cmd}`}
          >
            <code>{cmd}</code>
          </button>
        ))}
      </div>
    </div>
  );
}
