import { afterEach, describe, expect, it, vi } from "vitest"

import { OpenAPI } from "@/client"

import { AiJudgeService } from "./api"

describe("AiJudgeService.downloadExcel", () => {
  const originalToken = OpenAPI.TOKEN
  const originalBase = OpenAPI.BASE

  afterEach(() => {
    OpenAPI.TOKEN = originalToken
    OpenAPI.BASE = originalBase
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("passes endpoint url to token resolver", async () => {
    const tokenResolver = vi.fn(async (options: { url: string }) => {
      expect(options.url).toBe("/api/v1/rubric/download-excel")
      return "token-123"
    })

    const expectedBlob = new Blob(["excel-content"])
    const blobFn = vi.fn().mockResolvedValue(expectedBlob)
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: blobFn,
    })

    OpenAPI.TOKEN = tokenResolver as typeof OpenAPI.TOKEN
    OpenAPI.BASE = ""
    vi.stubGlobal("fetch", fetchMock)

    const result = await AiJudgeService.downloadExcel({
      items: [],
      summary: "test",
    })

    expect(result).toBe(expectedBlob)
    expect(tokenResolver).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/rubric/download-excel",
      expect.objectContaining({
        method: "POST",
      }),
    )
  })
})
