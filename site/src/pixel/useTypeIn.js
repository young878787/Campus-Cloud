import { useLayoutEffect } from "react";

/*
 * 只量看得到的字。跳過：讀屏用的隱藏文字（元素本身 1px，但不折行的字框會很長）、
 * visibility: hidden 的佔位字（輪播標語用最長的詞撐寬度，實際顯示的詞可能比較短）。
 */
function visibleTextRects(el) {
  const rects = [];
  const range = document.createRange();
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    const parentBox = parent.getBoundingClientRect();
    if (parentBox.width < 2 || parentBox.height < 2) continue;
    if (getComputedStyle(parent).visibility === "hidden") continue;
    range.selectNodeContents(node);
    rects.push(...range.getClientRects());
  }
  return rects;
}

/* 把同一行（垂直中心相近）的文字框併成一行：{ top, bottom, left, right }，座標相對於 box */
function measureLines(el) {
  const box = el.getBoundingClientRect();
  const lines = [];
  for (const r of visibleTextRects(el)) {
    if (r.width < 2 || r.height < 2) continue;
    const top = r.top - box.top;
    const bottom = r.bottom - box.top;
    const mid = (top + bottom) / 2;
    const line = lines.find((l) => Math.abs((l.top + l.bottom) / 2 - mid) < (bottom - top) / 2);
    if (line) {
      line.left = Math.min(line.left, r.left - box.left);
      line.right = Math.max(line.right, r.right - box.left);
      line.top = Math.min(line.top, top);
      line.bottom = Math.max(line.bottom, bottom);
    } else {
      lines.push({ top, bottom, left: r.left - box.left, right: r.right - box.left });
    }
  }
  return { width: box.width, lines: lines.sort((a, b) => a.top - b.top) };
}

/**
 * 開場打字（只跑一次）：字從左到右一格一格露出來，游標跟著走；字折成好幾行時，一行打完才打下一行。
 * 量出每一行的位置與寬度，排出每一格的 clip-path 與游標位置，交給 Web Animations 用 steps 跑。
 * textRef：要打出來的文字；caretRef：游標（絕對定位，跟文字同一個起點）。偏好減少動態效果時不跑。
 */
export default function useTypeIn(textRef, caretRef, { delay = 950, perStep = 45 } = {}) {
  useLayoutEffect(() => {
    const el = textRef.current;
    const caret = caretRef.current;
    if (!el || !caret || !el.animate) return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;

    // 等字型載好再量（不然行寬會量錯）；這段時間先藏起來，免得先閃出整句
    el.style.clipPath = "inset(0 0 100% 0)";
    let cancelled = false;
    const anims = [];
    const started = performance.now();

    (document.fonts?.ready ?? Promise.resolve()).then(() => {
      if (cancelled) return;
      el.style.clipPath = "";
      const { width, lines } = measureLines(el);
      if (!lines.length) return;
      const fontPx = parseFloat(getComputedStyle(el).fontSize) || 32;
      const clips = [];
      const carets = [];
      lines.forEach((line, k) => {
        const steps = Math.max(1, Math.round((line.right - line.left) / fontPx));
        for (let i = k === 0 ? 0 : 1; i <= steps; i += 1) {
          const x = line.left + ((line.right - line.left) * i) / steps;
          // 這一行以上整片露出，這一行露到 x
          clips.push(
            `polygon(0px 0px, ${width}px 0px, ${width}px ${line.top}px, ${x}px ${line.top}px, ${x}px ${line.bottom}px, 0px ${line.bottom}px)`,
          );
          const h = (line.bottom - line.top) * 0.8;
          carets.push(`translate(${x + fontPx * 0.08}px, ${line.top + (line.bottom - line.top) * 0.1}px) scaleY(${h / fontPx})`);
        }
      });
      const wait = Math.max(0, delay - (performance.now() - started));
      const duration = clips.length * perStep;
      const step = { easing: "steps(1, end)" };
      anims.push(el.animate(clips.map((clipPath) => ({ clipPath, ...step })), { duration, delay: wait, fill: "backwards" }));
      anims.push(
        caret.animate(
          carets.map((transform) => ({ transform, opacity: 1, ...step })),
          { duration, delay: wait, fill: "backwards" },
        ),
      );
      // 打完閃三下就收起來
      const last = carets[carets.length - 1];
      anims.push(
        caret.animate(
          [
            { transform: last, opacity: 1, ...step },
            { transform: last, opacity: 0, offset: 0.5, ...step },
            { transform: last, opacity: 0 },
          ],
          { duration: 300, delay: wait + duration, iterations: 3 },
        ),
      );
    });

    return () => {
      cancelled = true;
      el.style.clipPath = "";
      anims.forEach((a) => a.cancel());
    };
  }, [textRef, caretRef, delay, perStep]);
}
