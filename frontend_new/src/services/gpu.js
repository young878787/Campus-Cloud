import { apiGet } from "./api";

export const GpuService = {
  /**
   * 取得可用 GPU 選項
   * @param {{ startAt?: string, endAt?: string }} params
   */
  listOptions(params) {
    const query = new URLSearchParams();
    if (params?.startAt) query.set("start_at", params.startAt);
    if (params?.endAt)   query.set("end_at",   params.endAt);
    const qs = query.toString();
    return apiGet(`/api/v1/gpu/options${qs ? `?${qs}` : ""}`);
  },
};
