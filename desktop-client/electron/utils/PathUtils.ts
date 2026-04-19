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

  public static getFrpcLogStoragePath() {
    const result = path.join(PathUtils.getAppData(), "log");
    FileUtils.mkdir(result);
    return result;
  }

  public static getFrpcLogFilePath() {
    return path.join(PathUtils.getFrpcLogStoragePath(), "frpc.log");
  }

  public static getAppLogFilePath() {
    return path.join(app.getPath("logs"), "main.log");
  }

  public static getTomlConfigFilePath() {
    return path.join(PathUtils.getConfigStoragePath(), "frpc-visitor.toml");
  }

  public static getFrpcBinaryName() {
    return process.platform === "win32" ? "frpc.exe" : "frpc";
  }

  /**
   * Returns the path to the bundled frpc binary.
   * In dev, it's at <project>/bin/<name>; in production it's shipped via
   * electron-builder extraResources at process.resourcesPath/bin/<name>.
   */
  public static getBundledFrpcPath() {
    const name = PathUtils.getFrpcBinaryName();
    const packed = path.join(process.resourcesPath || "", "bin", name);
    if (fs.existsSync(packed)) return packed;
    return path.join(app.getAppPath(), "bin", name);
  }
}

export default PathUtils;
