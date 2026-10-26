import { afterEach, expect, test, vi } from "vitest";

const WINDOWS_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36";
const MAC_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

async function downloadUrl(
  apiUrl,
  { override = "", macOverride = "", userAgent = WINDOWS_UA, maxTouchPoints = 0 } = {},
) {
  vi.stubEnv("VITE_API_URL", apiUrl);
  vi.stubEnv("VITE_DESKTOP_CLIENT_DOWNLOAD_URL", override);
  vi.stubEnv("VITE_DESKTOP_CLIENT_MAC_DOWNLOAD_URL", macOverride);
  vi.stubGlobal("navigator", { userAgent, maxTouchPoints });
  return (await import("./desktopClient.js")).DESKTOP_CLIENT_DOWNLOAD_URL;
}

test("same-origin deployments use the backend download setting", async () => {
  expect(await downloadUrl("")).toBe("/api/v1/desktop-client/download");
});

test("split-origin deployments download through their configured API", async () => {
  expect(await downloadUrl("https://api.example.org/")).toBe(
    "https://api.example.org/api/v1/desktop-client/download",
  );
});

test("an explicit installer URL overrides the backend endpoint", async () => {
  const custom = "https://downloads.example.org/SkyLab-Connect-Setup.exe";
  expect(await downloadUrl("https://api.example.org", { override: custom })).toBe(
    custom,
  );
});

test("macOS browsers ask the backend for the macOS installer", async () => {
  expect(await downloadUrl("", { userAgent: MAC_UA })).toBe(
    "/api/v1/desktop-client/download?platform=mac",
  );
});

test("macOS uses its own override, never the Windows one", async () => {
  const windows = "https://downloads.example.org/SkyLab-Connect-Setup.exe";
  const mac = "https://downloads.example.org/SkyLab-Connect-mac-universal.dmg";
  expect(
    await downloadUrl("", { override: windows, userAgent: MAC_UA }),
  ).toBe("/api/v1/desktop-client/download?platform=mac");
  vi.resetModules();
  expect(
    await downloadUrl("", { override: windows, macOverride: mac, userAgent: MAC_UA }),
  ).toBe(mac);
});

test("iPads reporting a Mac user agent keep the default download", async () => {
  expect(await downloadUrl("", { userAgent: MAC_UA, maxTouchPoints: 5 })).toBe(
    "/api/v1/desktop-client/download",
  );
});
