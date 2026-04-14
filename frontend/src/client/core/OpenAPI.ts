import type { ApiRequestOptions } from "./ApiRequestOptions"

type Resolver<T> = (
  options: ApiRequestOptions<unknown>,
) => Promise<T | undefined> | T | undefined

type RequestPreparer = (
  options: ApiRequestOptions<unknown>,
) => Promise<void> | void

type Headers = Record<string, string>

class Interceptors<T> {
  #items = new Map<number, T>()
  #nextId = 0

  public use(interceptor: T): number {
    const id = this.#nextId
    this.#items.set(id, interceptor)
    this.#nextId += 1
    return id
  }

  public eject(id: number): void {
    this.#items.delete(id)
  }
}

export type OpenAPIConfig = {
  BASE: string
  VERSION: string
  WITH_CREDENTIALS: boolean
  CREDENTIALS: "include" | "omit" | "same-origin"
  TOKEN?: string | Resolver<string>
  USERNAME?: string | Resolver<string>
  PASSWORD?: string | Resolver<string>
  HEADERS?: Headers | Resolver<Headers>
  ENCODE_PATH?: (path: string) => string
  PREPARE_REQUEST?: RequestPreparer
  interceptors: {
    request: Interceptors<unknown>
    response: Interceptors<unknown>
  }
}

export const OpenAPI: OpenAPIConfig = {
  BASE: "",
  VERSION: "1.0.0",
  WITH_CREDENTIALS: false,
  CREDENTIALS: "include",
  TOKEN: undefined,
  USERNAME: undefined,
  PASSWORD: undefined,
  HEADERS: undefined,
  ENCODE_PATH: undefined,
  PREPARE_REQUEST: undefined,
  interceptors: {
    request: new Interceptors<unknown>(),
    response: new Interceptors<unknown>(),
  },
}