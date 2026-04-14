import axios from "axios"

import { ApiError } from "./ApiError"
import type { ApiRequestOptions } from "./ApiRequestOptions"
import type { ApiResult } from "./ApiResult"
import { CancelablePromise } from "./CancelablePromise"
import type { OpenAPIConfig } from "./OpenAPI"

const isDefined = <T>(value: T | null | undefined): value is T => {
  return value !== undefined && value !== null
}

const isString = (value: unknown): value is string => {
  return typeof value === "string"
}

const isStringWithValue = (value: unknown): value is string => {
  return isString(value) && value.length > 0
}

const isBlob = (value: unknown): value is Blob => {
  return typeof Blob !== "undefined" && value instanceof Blob
}

const isFile = (value: unknown): value is File => {
  return typeof File !== "undefined" && value instanceof File
}

const isFormData = (value: unknown): value is FormData => {
  return typeof FormData !== "undefined" && value instanceof FormData
}

const isPlainObject = (
  value: unknown,
): value is Record<string, unknown> => {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

const base64 = (value: string): string => {
  if (typeof globalThis.btoa === "function") {
    return globalThis.btoa(value)
  }
  return value
}

const resolveValue = async <T>(
  options: ApiRequestOptions<unknown>,
  resolver?: T | ((options: ApiRequestOptions<unknown>) => Promise<T> | T),
): Promise<T | undefined> => {
  if (typeof resolver === "function") {
    return await (resolver as (
      options: ApiRequestOptions<unknown>,
    ) => Promise<T> | T)(options)
  }
  return resolver
}

const appendQueryPair = (
  key: string,
  value: unknown,
  query: Array<string>,
): void => {
  if (!isDefined(value)) {
    return
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      appendQueryPair(key, item, query)
    }
    return
  }

  if (
    isPlainObject(value) &&
    !isBlob(value) &&
    !isFile(value) &&
    !isFormData(value) &&
    !(value instanceof Date)
  ) {
    for (const [nestedKey, nestedValue] of Object.entries(value)) {
      appendQueryPair(`${key}[${nestedKey}]`, nestedValue, query)
    }
    return
  }

  const serializedValue = value instanceof Date ? value.toISOString() : String(value)
  query.push(`${encodeURIComponent(key)}=${encodeURIComponent(serializedValue)}`)
}

const getQueryString = (params?: Record<string, unknown>): string => {
  if (!params) {
    return ""
  }

  const query: Array<string> = []

  for (const [key, value] of Object.entries(params)) {
    appendQueryPair(key, value, query)
  }

  return query.length > 0 ? `?${query.join("&")}` : ""
}

const getUrl = (
  config: OpenAPIConfig,
  options: ApiRequestOptions<unknown>,
): string => {
  const encoder = config.ENCODE_PATH ?? encodeURIComponent
  const path = options.url.replace(/\{(.*?)\}/g, (_, token: string) => {
    const value = options.path?.[token]
    return isDefined(value) ? encoder(String(value)) : ""
  })

  return `${config.BASE}${path}${getQueryString(options.query)}`
}

const appendFormValue = (
  formData: FormData,
  key: string,
  value: unknown,
): void => {
  if (!isDefined(value)) {
    return
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      appendFormValue(formData, key, item)
    }
    return
  }

  if (isBlob(value) || isFile(value) || isString(value)) {
    formData.append(key, value)
    return
  }

  formData.append(key, isPlainObject(value) ? JSON.stringify(value) : String(value))
}

const getFormData = (
  options: ApiRequestOptions<unknown>,
): FormData | undefined => {
  if (!options.formData) {
    return undefined
  }

  const formData = new FormData()

  for (const [key, value] of Object.entries(options.formData)) {
    appendFormValue(formData, key, value)
  }

  return formData
}

const getUrlEncodedBody = (
  values: Record<string, unknown>,
): URLSearchParams => {
  const searchParams = new URLSearchParams()

  for (const [key, value] of Object.entries(values)) {
    if (!isDefined(value)) {
      continue
    }

    if (Array.isArray(value)) {
      for (const item of value) {
        if (isDefined(item)) {
          searchParams.append(key, String(item))
        }
      }
      continue
    }

    searchParams.append(key, String(value))
  }

  return searchParams
}

const getRequestBody = (
  options: ApiRequestOptions<unknown>,
): unknown => {
  if (options.formData) {
    if (options.mediaType === "application/x-www-form-urlencoded") {
      return getUrlEncodedBody(options.formData)
    }
    return getFormData(options)
  }

  if (!isDefined(options.body)) {
    return undefined
  }

  if (
    options.mediaType === "application/x-www-form-urlencoded" &&
    isPlainObject(options.body)
  ) {
    return getUrlEncodedBody(options.body)
  }

  return options.body
}

const normalizeHeaders = (
  headers?: Record<string, unknown>,
): Record<string, string> => {
  const normalized: Record<string, string> = {}

  if (!headers) {
    return normalized
  }

  for (const [key, value] of Object.entries(headers)) {
    if (!isDefined(value)) {
      continue
    }
    normalized[key] = String(value)
  }

  return normalized
}

const getHeaders = async (
  config: OpenAPIConfig,
  options: ApiRequestOptions<unknown>,
): Promise<Record<string, string>> => {
  const [token, username, password, defaultHeaders] = await Promise.all([
    resolveValue(options, config.TOKEN),
    resolveValue(options, config.USERNAME),
    resolveValue(options, config.PASSWORD),
    resolveValue(options, config.HEADERS),
  ])

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...normalizeHeaders(defaultHeaders),
    ...normalizeHeaders(options.headers),
  }

  if (isStringWithValue(token)) {
    headers.Authorization = `Bearer ${token}`
  } else if (isStringWithValue(username) && isStringWithValue(password)) {
    headers.Authorization = `Basic ${base64(`${username}:${password}`)}`
  }

  if (options.mediaType) {
    headers["Content-Type"] = options.mediaType
  }

  if (options.formData && options.mediaType !== "application/x-www-form-urlencoded") {
    delete headers["Content-Type"]
  }

  return headers
}

const isSuccessStatus = (status: number): boolean => {
  return status >= 200 && status < 300
}

const getResponseBody = <T>(
  response: { data: unknown; headers: Record<string, unknown> },
  responseHeader?: string,
): T => {
  if (!responseHeader) {
    return response.data as T
  }

  return response.headers[responseHeader.toLowerCase()] as T
}

const catchErrorCodes = (
  options: ApiRequestOptions<unknown>,
  result: ApiResult,
): void => {
  const errors = options.errors ?? {}
  const message = errors[result.status]

  if (message) {
    throw new ApiError(options, result, message)
  }

  if (!result.ok) {
    throw new ApiError(options, result, result.statusText || "Request failed")
  }
}

export const request = <T>(
  config: OpenAPIConfig,
  options: ApiRequestOptions<unknown>,
): CancelablePromise<T> => {
  return new CancelablePromise<T>(async (resolve, reject, onCancel) => {
    const controller = new AbortController()
    onCancel(() => controller.abort())

    try {
      await config.PREPARE_REQUEST?.(options)

      const url = getUrl(config, options)
      const body = getRequestBody(options)
      const headers = await getHeaders(config, options)

      const response = await axios.request({
        url,
        method: options.method,
        data: body,
        headers,
        signal: controller.signal,
        withCredentials: config.WITH_CREDENTIALS,
        validateStatus: () => true,
      })

      const result: ApiResult = {
        url,
        ok: isSuccessStatus(response.status),
        status: response.status,
        statusText: response.statusText,
        body: response.data,
      }

      catchErrorCodes(options, result)
      resolve(getResponseBody<T>(response, options.responseHeader))
    } catch (error) {
      if (axios.isCancel(error)) {
        return
      }

      const axiosError = error instanceof Error ? error : new Error("Request failed")
      const result: ApiResult = {
        url: options.url,
        ok: false,
        status: 0,
        statusText: axiosError.message,
        body: error,
      }

      reject(new ApiError(options, result, axiosError.message))
    }
  })
}