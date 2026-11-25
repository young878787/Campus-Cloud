/**
 * 按鈕裡的「播放」小箭頭：像素階梯三角形。
 * 不用「▶」字元：iOS／Android 會把它換成彩色 emoji，跟像素風按鈕不搭。
 * 顏色跟著文字（currentColor）；固定一格 2px（8×14），階梯才不會糊。
 * 跟文字的間距交給外層的 flex gap。
 */
export default function PlayIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 4 7"
      width="8"
      height="14"
      shapeRendering="crispEdges"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "none", fill: "currentColor" }}
    >
      <path d="M0 0h1v7h-1zM1 1h1v5h-1zM2 2h1v3h-1zM3 3h1v1h-1z" />
    </svg>
  );
}
