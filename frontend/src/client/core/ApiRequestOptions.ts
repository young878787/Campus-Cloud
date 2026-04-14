export type ApiRequestOptions<T = unknown> = {
  readonly method:
    | "DELETE"
    | "GET"
    | "HEAD"
    | "OPTIONS"
    | "PATCH"
    | "POST"
    | "PUT"
  readonly url: string
  readonly path?: Record<string, unknown>
  readonly cookies?: Record<string, unknown>
  readonly headers?: Record<string, unknown>
  readonly query?: Record<string, unknown>
  readonly formData?: Record<string, unknown>
  readonly body?: T
  readonly mediaType?: string
  readonly responseHeader?: string
  readonly errors?: Record<number, string>
}