import { apiGet, apiPost } from "./api";

export const VmRequestsService = {
  /** 取得我的申請列表 */
  list() {
    return apiGet("/api/v1/vm-requests/");
  },

  /** 送出申請 */
  create(body) {
    return apiPost("/api/v1/vm-requests/", body);
  },

  /** 撤銷申請 */
  cancel(requestId) {
    return apiPost(`/api/v1/vm-requests/${requestId}/cancel`, {});
  },
};
