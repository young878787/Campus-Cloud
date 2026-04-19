import { net } from "electron";
import { BusinessError, ResponseCode } from "../core/BusinessError";
import Logger from "../core/Logger";
import SettingsService from "./SettingsService";

type HttpResult = {
  status: number;
  body: string;
};

class CampusCloudService {
  private readonly _settingsService: SettingsService;

  constructor(settingsService: SettingsService) {
    this._settingsService = settingsService;
  }

  private async request(
    method: string,
    pathname: string,
    options: { auth?: boolean; body?: any } = {}
  ): Promise<HttpResult> {
    const backendUrl = await this._settingsService.getBackendUrl();
    const url = backendUrl.replace(/\/$/, "") + pathname;
    return new Promise((resolve, reject) => {
      const req = net.request({ method, url });
      if (options.auth) {
        const token = ""; // resolved below
        // token resolution done after promise setup to keep code simple
      }
      if (options.body !== undefined) {
        req.setHeader("Content-Type", "application/json");
      }
      this._settingsService
        .getToken()
        .then(token => {
          if (options.auth && token) {
            req.setHeader("Authorization", `Bearer ${token}`);
          }
          let chunks: Buffer[] = [];
          req.on("response", response => {
            response.on("data", chunk => chunks.push(chunk));
            response.on("end", () => {
              resolve({
                status: response.statusCode,
                body: Buffer.concat(chunks).toString("utf-8")
              });
            });
            response.on("error", (err: Error) => reject(err));
          });
          req.on("error", (err: Error) => reject(err));
          if (options.body !== undefined) {
            req.write(JSON.stringify(options.body));
          }
          req.end();
        })
        .catch(reject);
    });
  }

  async requestDeviceCode(): Promise<DeviceCodeResponse> {
    const res = await this.request(
      "POST",
      "/api/v1/desktop-client/auth/device-code",
      { body: {} }
    );
    if (res.status !== 200) {
      Logger.warn(
        "CampusCloudService.requestDeviceCode",
        `status=${res.status} body=${res.body}`
      );
      throw new BusinessError(ResponseCode.BACKEND_ERROR, res.body);
    }
    return JSON.parse(res.body) as DeviceCodeResponse;
  }

  async pollDeviceCode(
    code: string
  ): Promise<{ status: string; accessToken: string | null }> {
    const res = await this.request(
      "GET",
      `/api/v1/desktop-client/auth/poll?code=${encodeURIComponent(code)}`
    );
    Logger.info(
      "CampusCloudService.pollDeviceCode",
      `status=${res.status} body=${res.body}`
    );
    if (res.status === 404) {
      throw new BusinessError(
        ResponseCode.LOGIN_TIMEOUT,
        "device code expired"
      );
    }
    if (res.status !== 200) {
      throw new BusinessError(ResponseCode.BACKEND_ERROR, res.body);
    }
    const data = JSON.parse(res.body);
    return {
      status: data.status,
      accessToken: data.access_token || null
    };
  }

  async listResources(): Promise<CampusCloudResource[]> {
    const res = await this.request("GET", "/api/v1/resources/my", {
      auth: true
    });
    if (res.status === 401) {
      throw new BusinessError(ResponseCode.NOT_LOGGED_IN);
    }
    if (res.status !== 200) {
      throw new BusinessError(ResponseCode.BACKEND_ERROR, res.body);
    }
    return JSON.parse(res.body) as CampusCloudResource[];
  }

  async getTunnelConfig(): Promise<CampusCloudTunnelConfig> {
    const res = await this.request("GET", "/api/v1/tunnel/my-config", {
      auth: true
    });
    if (res.status === 401) {
      throw new BusinessError(ResponseCode.NOT_LOGGED_IN);
    }
    if (res.status !== 200) {
      throw new BusinessError(ResponseCode.BACKEND_ERROR, res.body);
    }
    return JSON.parse(res.body) as CampusCloudTunnelConfig;
  }
}

export default CampusCloudService;
