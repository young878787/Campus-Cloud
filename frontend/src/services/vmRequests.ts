import type { CancelablePromise, VMRequestPublic } from "@/client"
import { OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"
import type { VmRequestCreateRequestBody } from "@/lib/resourcePayloads"

export const VmRequestsApi = {
  create(data: {
    requestBody: VmRequestCreateRequestBody
  }): CancelablePromise<VMRequestPublic> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/vm-requests/",
      body: data.requestBody,
      mediaType: "application/json",
      errors: { 422: "Validation Error" },
    })
  },

  cancel(data: { requestId: string }): CancelablePromise<VMRequestPublic> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/vm-requests/{request_id}/cancel",
      path: { request_id: data.requestId },
      errors: { 422: "Validation Error" },
    })
  },
}
