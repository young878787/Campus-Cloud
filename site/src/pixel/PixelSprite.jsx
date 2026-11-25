import { gridSize, rowsToPaths } from "../../../frontend/src/components/PixelArt/pixelArt";

/**
 * 字元格 → 像素 SVG（官網用的同款，資料與產生器跟平台前端共用 pixelArt.js）。
 * 不直接 import 前端的 PixelSprite.jsx：那份會用到前端那一份 React，官網會變成兩份 React。
 */
export default function PixelSprite({ rows, palette, cell, label, className = "", style }) {
  const { w, h } = gridSize(rows);
  const paths = rowsToPaths(rows);
  return (
    <svg
      className={className}
      viewBox={`0 0 ${w} ${h}`}
      width={cell ? w * cell : undefined}
      height={cell ? h * cell : undefined}
      shapeRendering="crispEdges"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : "true"}
      focusable="false"
      style={style}
    >
      {Object.entries(paths).map(([ch, d]) =>
        palette[ch] ? <path key={ch} d={d} style={{ fill: palette[ch] }} /> : null,
      )}
    </svg>
  );
}
