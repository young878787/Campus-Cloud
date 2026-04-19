interface ApiResponse<T> {
  bizCode: string;
  data: T;
  message: string;
}

interface ControllerParam {
  channel: string;
  event: Electron.IpcMainEvent;
  args: any;
}

interface ListenerParam {
  channel: string;
  args: any[];
}

type IpcRouter = {
  path: string;
  controller: string;
};

type Listener = {
  channel: string;
  listenerMethod: any;
};

enum IpcRouterKeys {
  AUTH = "AUTH",
  RESOURCE = "RESOURCE",
  TUNNEL = "TUNNEL",
  SETTINGS = "SETTINGS",
  LOG = "LOG",
  SYSTEM = "SYSTEM"
}

type IpcRouters = Record<
  IpcRouterKeys,
  {
    [method: string]: IpcRouter;
  }
>;

type Listeners = Record<string, Listener>;

// ─── Campus Cloud domain types ───────────────────────────────────────────────

interface CampusCloudSettings {
  _id?: string;
  language?: string;
  backendUrl?: string;
  token?: string;
  launchAtStartup?: boolean;
}

interface DeviceCodeResponse {
  device_code: string;
  login_url: string;
  expires_in: number;
}

interface CampusCloudResource {
  vmid: number;
  name: string;
  type: string;
  status: string;
  node?: string;
  ip_address?: string;
  environment_type?: string;
  [key: string]: any;
}

interface CampusCloudTunnelInfo {
  vmid?: number;
  name?: string;
  service?: string;
  visitor_port?: number;
  [key: string]: any;
}

interface CampusCloudTunnelConfig {
  frpc_config: string;
  tunnels: CampusCloudTunnelInfo[];
}

interface TunnelStatusInfo {
  running: boolean;
  lastStartTime: number;
  connectionError: string | null;
  tunnels: CampusCloudTunnelInfo[];
}
