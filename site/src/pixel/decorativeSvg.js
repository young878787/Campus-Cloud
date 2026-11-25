/**
 * 內嵌品牌 SVG（章魚動作、身分頭像）當裝飾用：拿掉檔案裡的 <title>。
 * 素材的 <title> 是中文（「管理員」「老師」…），內嵌後滑鼠停上去會跳出提示，英文、日文頁也是中文；
 * 這些圖旁邊都有文字說明、外層也設了 aria-hidden，不需要它。
 */
export function decorativeSvg(svg) {
  return svg.replace(/<title>[\s\S]*?<\/title>/g, "");
}
