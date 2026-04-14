/**
 * AI Judge API types and service
 */

import type { CancelablePromise } from "@/client"
import { OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

// ─── Types ────────────────────────────────────────────────────────────────────

export type RubricItem = {
  id: string
  title: string
  description: string
  max_score: number
  detectable: "auto" | "partial" | "manual"
  detection_method: string | null
  fallback: string | null
}

export type RubricAnalysis = {
  items: RubricItem[]
  total_score: number
  auto_count: number
  partial_count: number
  manual_count: number
  summary: string
  raw_text: string
}

export type ChatMessage = {
  role: "user" | "assistant"
  content: string
}

export type RubricUploadResponse = {
  analysis: RubricAnalysis
  ai_metrics: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    elapsed_seconds: number
    tokens_per_second: number
  }
}

export type RubricChatResponse = {
  reply: string
  updated_items: RubricItem[] | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  elapsed_seconds: number
  tokens_per_second: number
}

export type RubricHealthResponse = {
  status: string
  vllm_configured: boolean
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const AiJudgeService = {
  /**
   * Upload rubric document for AI analysis
   */
  uploadRubric(file: File): CancelablePromise<RubricUploadResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/rubric/upload",
      formData: { file },
    })
  },

  /**
   * Chat with AI to refine rubric
   */
  chat(data: {
    messages: ChatMessage[]
    rubric_context: string
    is_refine?: boolean
  }): CancelablePromise<RubricChatResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/rubric/chat",
      body: {
        messages: data.messages,
        rubric_context: data.rubric_context,
        is_refine: data.is_refine ?? false,
      },
      mediaType: "application/json",
    })
  },

  /**
   * Download rubric as Excel file
   */
  async downloadExcel(data: {
    items: RubricItem[]
    summary: string
  }): Promise<Blob> {
    // TOKEN can be a string or a Resolver function — resolve it first
    const rawToken = OpenAPI.TOKEN
    const token =
      typeof rawToken === "function"
        ? await (rawToken as (o: unknown) => Promise<string>)({})
        : rawToken

    const base = OpenAPI.BASE || ""
    const response = await fetch(`${base}/api/v1/rubric/download-excel`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        items: data.items,
        summary: data.summary,
      }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || "下載失敗")
    }

    return response.blob()
  },

  /**
   * Health check
   */
  healthCheck(): CancelablePromise<RubricHealthResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/rubric/health",
    })
  },
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Trigger file download from blob
 */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Format rubric analysis to context string for chat
 */
export function rubricToContext(analysis: RubricAnalysis): string {
  return JSON.stringify({
    items: analysis.items,
    total_score: analysis.total_score,
    summary: analysis.summary,
  })
}

/**
 * Get detectable status badge info
 */
export function getDetectableInfo(detectable: string) {
  switch (detectable) {
    case "auto":
      return {
        label: "可自動偵測",
        className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
      }
    case "partial":
      return {
        label: "部分可偵測",
        className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
      }
    case "manual":
    default:
      return {
        label: "需人工評閱",
        className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      }
  }
}
