// Follow the platform's configured release URL unless this deployment opts out.
const apiOrigin = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
const downloadEndpoint = `${apiOrigin}/api/v1/desktop-client/download`;

// iPadOS 的桌面版 Safari 也自稱 Macintosh，用觸控點數排除
function isMacDesktop() {
  if (typeof navigator === "undefined") return false;
  return (
    /Macintosh|Mac OS X/i.test(navigator.userAgent || "") &&
    !(navigator.maxTouchPoints > 1)
  );
}

export const DESKTOP_CLIENT_DOWNLOAD_URL = isMacDesktop()
  ? import.meta.env.VITE_DESKTOP_CLIENT_MAC_DOWNLOAD_URL ||
    `${downloadEndpoint}?platform=mac`
  : import.meta.env.VITE_DESKTOP_CLIENT_DOWNLOAD_URL || downloadEndpoint;
