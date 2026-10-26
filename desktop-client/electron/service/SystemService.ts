import { spawn } from "child_process";
import { app, shell } from "electron";
import fs from "fs";
import { isIP } from "net";
import path from "path";
import BeanFactory from "../core/BeanFactory";
import GlobalConstant from "../core/GlobalConstant";
import type SettingsService from "./SettingsService";

class SystemService {
  async openUrl(url: string) {
    const target = new URL(url);
    // 「開啟 Web 平台」開的是設定頁填的後端（SettingsService 已驗證過 HTTPS／本機
    // http），不只預設網址；只放行同一個 origin。
    const settingsService: SettingsService =
      BeanFactory.getBean("settingsService");
    const backendUrl = await settingsService.getBackendUrl();
    if (target.origin === new URL(backendUrl).origin) {
      await shell.openExternal(target.toString());
      return;
    }
    if (target.protocol !== "https:") throw new Error("URL must use HTTPS");
    const allowedHosts = new Set([
      "github.com",
      "objects.githubusercontent.com",
      "github-releases.githubusercontent.com",
      new URL(GlobalConstant.DEFAULT_BACKEND_URL).hostname
    ]);
    if (!allowedHosts.has(target.hostname))
      throw new Error("URL host is not allowed");
    await shell.openExternal(target.toString());
  }

  async relaunch() {
    app.relaunch();
    app.quit();
  }

  openLocalFile(filePath: string): Promise<boolean> {
    return new Promise<boolean>((resolve, reject) => {
      shell
        .openPath(filePath)
        .then(errorMessage => {
          resolve(!errorMessage);
        })
        .catch(reject);
    });
  }

  openLocalPath(localPath: string): Promise<boolean> {
    return new Promise<boolean>(resolve => {
      shell.openPath(localPath).then(errorMessage => {
        resolve(!errorMessage);
      });
    });
  }

  async openSsh(
    port: number,
    user = "root",
    host = "127.0.0.1"
  ): Promise<void> {
    if (
      !Number.isInteger(port) ||
      port <= 0 ||
      port > 65535 ||
      isIP(host) !== 4 ||
      !/^[A-Za-z0-9._-]+$/.test(user)
    ) {
      throw new Error("Invalid SSH target");
    }
    const sshCmd = `ssh -o StrictHostKeyChecking=accept-new -p ${port} ${user}@${host}`;
    if (process.platform === "win32") {
      await this._spawnDetached("cmd.exe", [
        "/d",
        "/k",
        `title SkyLab SSH - ${host}:${port} & ${sshCmd}`
      ]);
    } else if (process.platform === "darwin") {
      const escapedCmd = sshCmd.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      const script = [
        'tell application "Terminal"',
        "activate",
        `do script "${escapedCmd}"`,
        "end tell"
      ].join("\n");
      await this._spawnDetached("osascript", ["-e", script]);
    } else {
      spawn("x-terminal-emulator", ["-e", "sh", "-c", sshCmd], {
        detached: true,
        stdio: "ignore"
      }).unref();
    }
  }

  private _hasMacRdpClient(): boolean {
    try {
      if (
        typeof app.getApplicationNameForProtocol === "function" &&
        app.getApplicationNameForProtocol("rdp://")
      ) {
        return true;
      }
    } catch {
      // Fall through to application bundle check.
    }
    const home = app.getPath("home");
    const candidates = [
      "/Applications/Windows App.app",
      "/Applications/Microsoft Remote Desktop.app",
      path.join(home, "Applications", "Windows App.app"),
      path.join(home, "Applications", "Microsoft Remote Desktop.app")
    ];
    return candidates.some(candidate => fs.existsSync(candidate));
  }

  private async _macRdpMissingMessage(): Promise<string> {
    try {
      const settingsService: SettingsService =
        BeanFactory.getBean("settingsService");
      const lang = await settingsService.getLanguage();
      if (lang === "zh-TW") {
        return "尚未安裝 RDP 遠端桌面軟體，請先至 Mac App Store 免費下載 Microsoft「Windows App」（原名 Microsoft Remote Desktop）。";
      }
      if (lang === "ja") {
        return "RDP クライアントが見つかりません。Mac App Store から Microsoft「Windows App」（旧 Microsoft Remote Desktop）をインストールしてください。";
      }
    } catch {
      // Default to English below.
    }
    return "No RDP client found. Please install Microsoft 'Windows App' (formerly Microsoft Remote Desktop) from the Mac App Store.";
  }

  async openRdp(port: number, host = "127.0.0.1"): Promise<void> {
    if (
      !Number.isInteger(port) ||
      port <= 0 ||
      port > 65535 ||
      isIP(host) !== 4
    ) {
      throw new Error("Invalid RDP target");
    }
    const target = `${host}:${port}`;
    if (process.platform === "win32") {
      await this._spawnDetached("mstsc.exe", [`/v:${target}`]);
      return;
    }
    if (process.platform === "darwin") {
      if (!this._hasMacRdpClient()) {
        throw new Error(await this._macRdpMissingMessage());
      }
      await shell.openExternal(`rdp://full%20address=s:${target}`);
      return;
    }
    await this._spawnDetached("xfreerdp", [`/v:${target}`]);
  }

  private _spawnDetached(command: string, args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
      const child = spawn(command, args, {
        detached: true,
        stdio: "ignore",
        windowsHide: false
      });
      child.once("error", reject);
      child.once("spawn", () => {
        child.unref();
        resolve();
      });
    });
  }
}

export default SystemService;
