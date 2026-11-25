import { useEffect, useRef } from "react";
import { DOTS, PLUS, SPARKLE } from "../../../frontend/src/components/PixelArt/pixelArt";
import { SKY_CLOUDS } from "../../../frontend/src/components/PixelArt/pixelScenery";
import PixelSprite from "./PixelSprite";
import styles from "./PixelLanding.module.scss";

const CLOUD = { f: "var(--px-sky-cloud)", s: "var(--px-sky-cloud-shade)" };
const GOLD = { x: "var(--px-gold)", X: "var(--px-gold-hi)" };
const BLUE = { x: "var(--px-star-blue)", X: "var(--px-star-blue)" };
const DOT = { x: "var(--px-dots)" };

/*
 * 像素天空（同登入頁的白天天空）：柔和雲慢慢飄、金藍十字星一閃一閃、點點方陣。
 * 位置用所在區塊的百分比；depth 越大跟游標視差移得越多（越近）。wide 只在寬版面放（窄的時候會壓到字）。
 * 夜晚雲換成夜空色（--px-sky-cloud）。第一屏與結尾各一組版面（HERO_SKY／OUTRO_SKY）。
 */
const HERO_CLOUDS = [
  { rows: SKY_CLOUDS.c, cell: 6, left: "-3%", top: "6%", depth: 0.35, drift: "skyDriftA" },
  { rows: SKY_CLOUDS.b, cell: 5, left: "42%", top: "4%", depth: 0.2, drift: "skyDriftB" },
  { rows: SKY_CLOUDS.a, cell: 6, left: "84%", top: "10%", depth: 0.5, drift: "skyDriftB" },
  { rows: SKY_CLOUDS.d, cell: 5, left: "56%", top: "80%", depth: 0.25, drift: "skyDriftA" },
  { rows: SKY_CLOUDS.b, cell: 4, left: "6%", top: "86%", depth: 0.3, drift: "skyDriftB" },
];

const HERO_STARS = [
  { rows: PLUS, palette: GOLD, cell: 5, left: "38%", top: "16%" },
  { rows: SPARKLE, palette: GOLD, cell: 4, left: "95%", top: "52%" },
  { rows: PLUS, palette: BLUE, cell: 4, left: "2%", top: "58%" },
  { rows: SPARKLE, palette: BLUE, cell: 3, left: "50%", top: "62%", wide: true },
  { rows: PLUS, palette: GOLD, cell: 4, left: "78%", top: "88%" },
  { rows: PLUS, palette: BLUE, cell: 3, left: "30%", top: "92%", wide: true },
];

const HERO_DOTS = [
  { left: "47%", top: "30%" },
  { left: "90%", top: "78%" },
];

export const HERO_SKY = { clouds: HERO_CLOUDS, stars: HERO_STARS, dots: HERO_DOTS };

/* 結尾：雲與星排在標題與按鈕的兩側，底下留給雲海 */
export const OUTRO_SKY = {
  clouds: [
    { rows: SKY_CLOUDS.a, cell: 6, left: "4%", top: "10%", depth: 0.4, drift: "skyDriftA" },
    { rows: SKY_CLOUDS.d, cell: 5, left: "20%", top: "46%", depth: 0.25, drift: "skyDriftB", wide: true },
    { rows: SKY_CLOUDS.c, cell: 5, left: "74%", top: "6%", depth: 0.35, drift: "skyDriftB" },
    { rows: SKY_CLOUDS.b, cell: 4, left: "82%", top: "48%", depth: 0.3, drift: "skyDriftA", wide: true },
  ],
  stars: [
    { rows: SPARKLE, palette: GOLD, cell: 4, left: "26%", top: "18%" },
    { rows: PLUS, palette: BLUE, cell: 4, left: "12%", top: "34%" },
    { rows: PLUS, palette: GOLD, cell: 4, left: "70%", top: "36%" },
    { rows: SPARKLE, palette: BLUE, cell: 3, left: "92%", top: "26%", wide: true },
    { rows: PLUS, palette: BLUE, cell: 3, left: "64%", top: "14%", wide: true },
  ],
  dots: [
    { left: "8%", top: "56%" },
    { left: "88%", top: "12%" },
  ],
};

export default function SkyLayer({ layout = HERO_SKY }) {
  const rootRef = useRef(null);

  /* 跟游標一點點視差（偏好減少動態效果時不動） */
  useEffect(() => {
    const root = rootRef.current;
    if (!root || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    let raf = 0;
    let target = { x: 0, y: 0 };
    const apply = () => {
      raf = 0;
      root.style.setProperty("--sky-px", target.x.toFixed(3));
      root.style.setProperty("--sky-py", target.y.toFixed(3));
    };
    const onMove = (e) => {
      target = { x: (e.clientX / window.innerWidth) * 2 - 1, y: (e.clientY / window.innerHeight) * 2 - 1 };
      if (!raf) raf = window.requestAnimationFrame(apply);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div className={styles.heroSky} ref={rootRef} aria-hidden="true">
      {layout.clouds.map((c, i) => (
        <div
          key={`c${i}`}
          className={`${styles.skyItem} ${c.wide ? styles.skyWide : ""}`}
          style={{ left: c.left, top: c.top, "--depth": c.depth }}
        >
          <PixelSprite className={styles[c.drift]} rows={c.rows} palette={CLOUD} cell={c.cell} />
        </div>
      ))}
      {layout.dots.map((d, i) => (
        <div key={`d${i}`} className={`${styles.skyItem} ${styles.skyWide}`} style={{ left: d.left, top: d.top, "--depth": 0.1 }}>
          <PixelSprite rows={DOTS} palette={DOT} cell={4} />
        </div>
      ))}
      {layout.stars.map((s, i) => (
        <div
          key={`s${i}`}
          className={`${styles.skyItem} ${s.wide ? styles.skyWide : ""}`}
          style={{ left: s.left, top: s.top, "--depth": 0.15 }}
        >
          <PixelSprite
            className={styles.skyStar}
            rows={s.rows}
            palette={s.palette}
            cell={s.cell}
            style={{ animationDelay: `${i * -0.7}s` }}
          />
        </div>
      ))}
    </div>
  );
}
