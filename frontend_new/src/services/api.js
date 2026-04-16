/**
 * api.js
 * 統一的 API 請求入口。
 * - 自動帶入 Authorization header
 * - 統一錯誤格式：失敗時 throw { status, message }
 *
 * 使用方式：
 *   import { apiGet, apiPost } from "@/services/api";
 *   const user = await apiGet("/api/v1/users/me");
 */

import { AuthStorage } from "./auth";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

/** 建立共用 headers */
function buildHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = AuthStorage.getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

/** 統一處理 response */
async function handleResponse(res) {
  if (res.ok) {
    // 204 No Content 不會有 body
    return res.status === 204 ? null : res.json();
  }

  let message = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    message = body?.detail ?? body?.message ?? message;
  } catch {
    // 若 body 不是 JSON 就用預設訊息
  }

  throw { status: res.status, message };
}

/** GET */
export function apiGet(path) {
  return fetch(`${BASE_URL}${path}`, {
    method: "GET",
    headers: buildHeaders(),
  }).then(handleResponse);
}

/** POST（JSON body） */
export function apiPost(path, body) {
  return fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  }).then(handleResponse);
}

/** POST（form-urlencoded，登入用） */
export function apiPostForm(path, params) {
  return fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(params).toString(),
  }).then(handleResponse);
}

/** PATCH */
export function apiPatch(path, body) {
  return fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  }).then(handleResponse);
}

/** DELETE */
export function apiDelete(path) {
  return fetch(`${BASE_URL}${path}`, {
    method: "DELETE",
    headers: buildHeaders(),
  }).then(handleResponse);
}
