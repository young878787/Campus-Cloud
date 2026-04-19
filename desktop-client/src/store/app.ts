import { on, onListener, send } from "@/utils/ipcUtils";
import { defineStore } from "pinia";
import { ipcRouters, listeners } from "../../electron/core/IpcRouter";

interface AppState {
  loggedIn: boolean;
  loginInProgress: boolean;
  language: string;
  autoStart: boolean;
  tunnelStatus: TunnelStatusInfo;
  resources: CampusCloudResource[];
}

const DEFAULT_TUNNEL_STATUS: TunnelStatusInfo = {
  running: false,
  lastStartTime: -1,
  connectionError: null,
  tunnels: []
};

export const useAppStore = defineStore("app", {
  state: (): AppState => ({
    loggedIn: false,
    loginInProgress: false,
    language: "zh-CN",
    autoStart: false,
    tunnelStatus: { ...DEFAULT_TUNNEL_STATUS },
    resources: []
  }),
  actions: {
    registerListeners() {
      on(ipcRouters.AUTH.getAuthState, data => {
        this.loggedIn = !!data.loggedIn;
        this.loginInProgress = !!data.loginInProgress;
      });
      on(ipcRouters.SETTINGS.getSettings, data => {
        if (data) {
          this.language = data.language || "zh-CN";
          this.autoStart = !!data.launchAtStartup;
        }
      });
      on(ipcRouters.SETTINGS.saveSettings, data => {
        if (data) {
          this.language = data.language || this.language;
          this.autoStart = !!data.launchAtStartup;
        }
      });
      on(ipcRouters.RESOURCE.listMyResources, data => {
        this.resources = Array.isArray(data) ? data : [];
      });
      onListener(listeners.watchTunnel, (data: TunnelStatusInfo) => {
        this.tunnelStatus = data;
      });
    },
    refreshAuth() {
      send(ipcRouters.AUTH.getAuthState);
    },
    refreshSettings() {
      send(ipcRouters.SETTINGS.getSettings);
    },
    refreshResources() {
      send(ipcRouters.RESOURCE.listMyResources);
    },
    logout() {
      send(ipcRouters.AUTH.logout);
      this.loggedIn = false;
    }
  }
});
