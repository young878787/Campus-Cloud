/* biome-ignore-all lint/complexity/noStaticOnlyClass: legacy client compatibility surface intentionally mirrors the previous generated API */

import type * as ClientTypes from "./types.gen"
import { OpenAPI } from "./core/OpenAPI"
import { request as __request } from "./core/request"

type ResourceConfig = {
  cores?: number
  memory?: number
  [key: string]: unknown
}

type ResourceOverview = ClientTypes.VmSchema & {
  ip_address?: string | null
  environment_type?: string | null
  os_info?: string | null
  expiry_date?: string | null
  ssh_public_key?: string | null
}

const validationError = { 422: "Validation Error" } as const

export class AiTemplateRecommendationService {
  public static chat(data: { requestBody: ClientTypes.ChatRequest }) {
    return __request<ClientTypes.ChatResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/ai/template-recommendation/chat",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static recommend(data: {
    requestBody: ClientTypes.ChatRequest
  }) {
    return __request<Record<string, unknown>>(OpenAPI, {
      method: "POST",
      url: "/api/v1/ai/template-recommendation/recommend",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class LoginService {
  public static loginAccessToken(data: {
    formData: ClientTypes.BodyLoginLoginAccessToken
  }) {
    return __request<ClientTypes.Token>(OpenAPI, {
      method: "POST",
      url: "/api/v1/login/access-token",
      formData: data.formData,
      mediaType: "application/x-www-form-urlencoded",
      errors: validationError,
    })
  }

  public static recoverPassword(data: { email: string }) {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "POST",
      url: "/api/v1/password-recovery/{email}",
      path: { email: data.email },
      errors: validationError,
    })
  }

  public static resetPassword(data: {
    requestBody: ClientTypes.NewPassword
  }) {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "POST",
      url: "/api/v1/reset-password/",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class UsersService {
  public static readUsers(data: { skip?: number; limit?: number } = {}) {
    return __request<ClientTypes.UsersPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/users/",
      query: data,
      errors: validationError,
    })
  }

  public static createUser(data: { requestBody: ClientTypes.UserCreate }) {
    return __request<ClientTypes.UserPublic>(OpenAPI, {
      method: "POST",
      url: "/api/v1/users/",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static deleteUserMe() {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/users/me",
    })
  }

  public static readUserMe() {
    return __request<ClientTypes.UserPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/users/me",
    })
  }

  public static updateUserMe(data: {
    requestBody: ClientTypes.UserUpdateMe
  }) {
    return __request<ClientTypes.UserPublic>(OpenAPI, {
      method: "PATCH",
      url: "/api/v1/users/me",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static updatePasswordMe(data: {
    requestBody: ClientTypes.UpdatePassword
  }) {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "PATCH",
      url: "/api/v1/users/me/password",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static registerUser(data: {
    requestBody: ClientTypes.UserRegister
  }) {
    return __request<ClientTypes.UserPublic>(OpenAPI, {
      method: "POST",
      url: "/api/v1/users/signup",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static deleteUser(data: { userId: string }) {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/users/{userId}",
      path: { userId: data.userId },
      errors: validationError,
    })
  }

  public static updateUser(data: {
    userId: string
    requestBody: ClientTypes.UserUpdate
  }) {
    return __request<ClientTypes.UserPublic>(OpenAPI, {
      method: "PATCH",
      url: "/api/v1/users/{userId}",
      path: { userId: data.userId },
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class GroupsService {
  public static listGroups() {
    return __request<ClientTypes.GroupsPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/groups/",
    })
  }

  public static getGroup(data: { groupId: string }) {
    return __request<ClientTypes.GroupDetailPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/groups/{groupId}",
      path: { groupId: data.groupId },
      errors: validationError,
    })
  }

  public static createGroup(data: {
    requestBody: ClientTypes.GroupCreate
  }) {
    return __request<ClientTypes.GroupPublic>(OpenAPI, {
      method: "POST",
      url: "/api/v1/groups/",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static deleteGroup(data: { groupId: string }) {
    return __request<unknown>(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/groups/{groupId}",
      path: { groupId: data.groupId },
      errors: validationError,
    })
  }

  public static addMembers(data: {
    groupId: string
    requestBody: ClientTypes.GroupMemberAdd
  }) {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "POST",
      url: "/api/v1/groups/{groupId}/members",
      path: { groupId: data.groupId },
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static removeMember(data: {
    groupId: string
    userId: string
  }) {
    return __request<ClientTypes.Message>(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/groups/{groupId}/members/{userId}",
      path: { groupId: data.groupId, userId: data.userId },
      errors: validationError,
    })
  }
}

export class VmRequestsService {
  public static listMyVmRequests(data: {
    skip?: number
    limit?: number
  } = {}) {
    return __request<ClientTypes.VmRequestsPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/vm-requests/my",
      query: data,
      errors: validationError,
    })
  }

  public static listAllVmRequests(data: {
    status?: ClientTypes.VmRequestStatus | null
    skip?: number
    limit?: number
  } = {}) {
    return __request<ClientTypes.VmRequestsPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/vm-requests/",
      query: data,
      errors: validationError,
    })
  }

  public static reviewVmRequest(data: {
    requestId: string
    requestBody: ClientTypes.VmRequestReview
  }) {
    return __request<ClientTypes.VmRequestPublic>(OpenAPI, {
      method: "POST",
      url: "/api/v1/vm-requests/{requestId}/review",
      path: { requestId: data.requestId },
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class VmService {
  public static getVmTemplates() {
    return __request<Array<ClientTypes.VmTemplateSchema>>(OpenAPI, {
      method: "GET",
      url: "/api/v1/vm/templates",
    })
  }

  public static createVm(data: {
    requestBody: ClientTypes.VmCreateRequest
  }) {
    return __request<ClientTypes.VmCreateResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/vm/create",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class LxcService {
  public static getTemplates() {
    return __request<Array<ClientTypes.TemplateSchema>>(OpenAPI, {
      method: "GET",
      url: "/api/v1/lxc/templates",
    })
  }

  public static createLxc(data: {
    requestBody: ClientTypes.LxcCreateRequest
  }) {
    return __request<ClientTypes.LxcCreateResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/lxc/create",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class ResourcesService {
  public static listResources(data: { node?: string | null } = {}) {
    return __request<Array<ClientTypes.ResourcePublic>>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/",
      query: data,
      errors: validationError,
    })
  }

  public static listMyResources() {
    return __request<Array<ClientTypes.ResourcePublic>>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/my",
    })
  }

  public static getResource(data: { vmid: number }) {
    return __request<ResourceOverview>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/{vmid}",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static getResourceConfig(data: { vmid: number }) {
    return __request<ResourceConfig>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/{vmid}/config",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static startResource(data: { vmid: number }) {
    return __request<unknown>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/start",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static stopResource(data: { vmid: number }) {
    return __request<unknown>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/stop",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static rebootResource(data: { vmid: number }) {
    return __request<unknown>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/reboot",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static shutdownResource(data: { vmid: number }) {
    return __request<unknown>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/shutdown",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static resetResource(data: { vmid: number }) {
    return __request<unknown>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/reset",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static deleteResource(data: {
    vmid: number
    purge?: boolean
    force?: boolean
  }) {
    return __request<unknown>(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/resources/{vmid}",
      path: { vmid: data.vmid },
      query: {
        purge: data.purge,
        force: data.force,
      },
      errors: validationError,
    })
  }

  public static getSshKey(data: { vmid: number }) {
    return __request<ClientTypes.SshKeyResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/{vmid}/ssh-key",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }
}

export class ResourceDetailsService {
  public static getCurrentStats(data: { vmid: number }) {
    return __request<ClientTypes.CurrentStatsResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/{vmid}/current-stats",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static getRrdStats(data: { vmid: number; timeframe?: string }) {
    return __request<ClientTypes.RrdDataResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/{vmid}/stats",
      path: { vmid: data.vmid },
      query: { timeframe: data.timeframe },
      errors: validationError,
    })
  }

  public static listSnapshots(data: { vmid: number }) {
    return __request<Array<ClientTypes.SnapshotInfo>>(OpenAPI, {
      method: "GET",
      url: "/api/v1/resources/{vmid}/snapshots",
      path: { vmid: data.vmid },
      errors: validationError,
    })
  }

  public static createSnapshot(data: {
    vmid: number
    requestBody: ClientTypes.SnapshotCreateRequest
  }) {
    return __request<ClientTypes.SnapshotResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/snapshots",
      path: { vmid: data.vmid },
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static deleteSnapshot(data: { vmid: number; snapname: string }) {
    return __request<ClientTypes.SnapshotResponse>(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/resources/{vmid}/snapshots/{snapname}",
      path: { vmid: data.vmid, snapname: data.snapname },
      errors: validationError,
    })
  }

  public static rollbackSnapshot(data: { vmid: number; snapname: string }) {
    return __request<ClientTypes.SnapshotResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/resources/{vmid}/snapshots/{snapname}/rollback",
      path: { vmid: data.vmid, snapname: data.snapname },
      errors: validationError,
    })
  }

  public static directUpdateSpec(data: {
    vmid: number
    requestBody: ClientTypes.DirectSpecUpdateRequest
  }) {
    return __request<unknown>(OpenAPI, {
      method: "PUT",
      url: "/api/v1/resources/{vmid}/spec/direct",
      path: { vmid: data.vmid },
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class SpecChangeRequestsService {
  public static createSpecChangeRequest(data: {
    requestBody: ClientTypes.SpecChangeRequestCreate
  }) {
    return __request<ClientTypes.SpecChangeRequestPublic>(OpenAPI, {
      method: "POST",
      url: "/api/v1/spec-change-requests/",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }
}

export class AuditLogsService {
  public static getResourceAuditLogs(data: {
    vmid: number
    skip?: number
    limit?: number
  }) {
    return __request<ClientTypes.AuditLogsPublic>(OpenAPI, {
      method: "GET",
      url: "/api/v1/audit-logs/resources/{vmid}",
      path: { vmid: data.vmid },
      query: {
        skip: data.skip,
        limit: data.limit,
      },
      errors: validationError,
    })
  }
}

export class ScriptDeployService {
  public static deployServiceTemplate(data: {
    requestBody: ClientTypes.ScriptDeployRequest
  }) {
    return __request<ClientTypes.ScriptDeployResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/script-deploy/deploy",
      body: data.requestBody,
      mediaType: "application/json",
      errors: validationError,
    })
  }

  public static getDeployStatus(data: { taskId: string }) {
    return __request<ClientTypes.ScriptDeployStatus>(OpenAPI, {
      method: "GET",
      url: "/api/v1/script-deploy/status/{taskId}",
      path: { taskId: data.taskId },
      errors: validationError,
    })
  }

  public static registerDeployedResource(data: { taskId: string }) {
    return __request<Record<string, unknown>>(OpenAPI, {
      method: "POST",
      url: "/api/v1/script-deploy/register/{taskId}",
      path: { taskId: data.taskId },
      errors: validationError,
    })
  }
}