/**
 * Gateway VM 管理 API 服務
 */

import type { CancelablePromise } from "@/client"
import { OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

export type GatewayConfigPublic = {
  host: string
  ssh_port: number
  ssh_user: string
  public_key: string
  is_configured: boolean
}

export type GatewayConfigUpdate = {
  host: string
  ssh_port: number
  ssh_user: string
}

export type GatewayConnectionTestResult = {
  success: boolean
  message: string
}

export type ServiceConfigRead = {
  service: string
  content: string
}

export type ServiceStatusResult = {
  service: string
  active: boolean
  status_text: string
}

export type ServiceActionResult = {
  service: string
  action: string
  success: boolean
  output: string
}

export type GatewayService = "haproxy" | "traefik" | "frps" | "frpc"
export type ServiceAction = "start" | "stop" | "restart" | "reload"

export class GatewayApiService {
  /** 取得 Gateway VM 連線設定 */
  static getConfig(): CancelablePromise<GatewayConfigPublic> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/gateway/config",
    })
  }

  /** 更新連線設定 */
  static updateConfig(
    data: GatewayConfigUpdate,
  ): CancelablePromise<GatewayConfigPublic> {
    return __request(OpenAPI, {
      method: "PUT",
      url: "/api/v1/gateway/config",
      body: data,
      mediaType: "application/json",
    })
  }

  /** 生成新的 SSH Keypair */
  static generateKeypair(): CancelablePromise<GatewayConfigPublic> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/gateway/generate-keypair",
    })
  }

  /** 測試 SSH 連線 */
  static testConnection(): CancelablePromise<GatewayConnectionTestResult> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/gateway/test-connection",
    })
  }

  /** 讀取服務設定檔 */
  static readServiceConfig(
    service: GatewayService,
  ): CancelablePromise<ServiceConfigRead> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/gateway/services/{service}/config",
      path: { service },
    })
  }

  /** 寫入服務設定檔 */
  static writeServiceConfig(
    service: GatewayService,
    content: string,
  ): CancelablePromise<{ message: string }> {
    return __request(OpenAPI, {
      method: "PUT",
      url: "/api/v1/gateway/services/{service}/config",
      path: { service },
      body: { content },
      mediaType: "application/json",
    })
  }

  /** 取得服務狀態 */
  static getServiceStatus(
    service: GatewayService,
  ): CancelablePromise<ServiceStatusResult> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/gateway/services/{service}/status",
      path: { service },
    })
  }

  /** 控制服務 */
  static controlService(
    service: GatewayService,
    action: ServiceAction,
  ): CancelablePromise<ServiceActionResult> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/gateway/services/{service}/{action}",
      path: { service, action },
    })
  }

  /** 取得安裝腳本下載 URL */
  static getInstallScriptUrl(): string {
    return `${OpenAPI.BASE}/api/v1/gateway/install-script`
  }
}
