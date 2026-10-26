import { app } from "electron";
import path from "path";
import fs from "fs";
import FileUtils from "./FileUtils";

class PathUtils {
  public static getAppData() {
    return app.getPath("userData");
  }

  public static getConfigStoragePath() {
    const result = path.join(PathUtils.getAppData(), "config");
    FileUtils.mkdir(result);
    return result;
  }

  public static getDataBaseStoragePath() {
    const result = path.join(PathUtils.getAppData(), "db");
    FileUtils.mkdir(result);
    return result;
  }

  public static getAppLogFilePath() {
    return path.join(app.getPath("logs"), "main.log");
  }

  public static getWireGuardConfigFilePath() {
    return path.join(PathUtils.getConfigStoragePath(), "SkyLab.conf");
  }

  public static getWireGuardIdentityFilePath(scope?: string) {
    if (scope !== undefined && !/^[a-f0-9]{64}$/.test(scope)) {
      throw new Error("Invalid WireGuard identity scope");
    }
    return path.join(
      PathUtils.getConfigStoragePath(),
      scope ? `wireguard-identity-${scope}.json` : "wireguard-identity.json"
    );
  }

  public static getBundledWireGuardInstallerPath() {
    const filename = "wireguard-amd64-1.1.msi";
    const packed = path.join(
      process.resourcesPath || "",
      "wireguard",
      filename
    );
    if (app.isPackaged || fs.existsSync(packed)) return packed;
    return path.join(app.getAppPath(), "vendor", "wireguard", filename);
  }

  public static getBundledMacWireGuardDir() {
    const packed = path.join(process.resourcesPath || "", "wireguard");
    if (
      app.isPackaged ||
      fs.existsSync(path.join(packed, "skylab-wg-helper.sh"))
    ) {
      return packed;
    }
    return path.join(app.getAppPath(), "vendor", "wireguard-mac");
  }

  public static getInstalledMacWireGuardHelperPath() {
    return "/Library/Application Support/SkyLabConnect/wireguard/skylab-wg-helper";
  }

  public static getInstalledMacWireGuardVersionPath() {
    return "/Library/Application Support/SkyLabConnect/wireguard/version";
  }

  public static getMacTunnelNameFilePath() {
    return "/var/run/wireguard/SkyLab.name";
  }

  /** 第三方授權聲明：打包後在 resources 根目錄（electron-builder extraResources），開發時讀專案根目錄 */
  public static getThirdPartyNoticesPath() {
    const filename = "THIRD_PARTY_NOTICES.txt";
    const packed = path.join(process.resourcesPath || "", filename);
    if (app.isPackaged || fs.existsSync(packed)) return packed;
    return path.join(app.getAppPath(), filename);
  }
}

export default PathUtils;
