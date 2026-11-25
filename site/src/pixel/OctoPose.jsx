import { decorativeSvg } from "./decorativeSvg";
import styles from "./PixelLanding.module.scss";

/* 品牌素材的章魚學士動作（桌面「品牌元素\章魚動作\svg」，32×26 像素畫布），直接內嵌 svg 才能用 CSS 換深色模式的顏色 */
const POSES = import.meta.glob("./assets/octo/*.svg", { query: "?raw", import: "default", eager: true });

function svgOf(name) {
  return decorativeSvg(POSES[`./assets/octo/${name}.svg`] ?? "");
}

/**
 * 一個章魚動作（搬伺服器、資安守護、拿放大鏡…）。純裝飾：意思由旁邊的文字講，所以對螢幕閱讀器隱藏。
 * 大小由 className 設 --pose-w（32 的倍數像素才不糊），窄螢幕可以在 media query 裡改。
 */
export default function OctoPose({ name, className = "" }) {
  return (
    <span className={`${styles.pose} ${className}`} aria-hidden="true" dangerouslySetInnerHTML={{ __html: svgOf(name) }} />
  );
}
