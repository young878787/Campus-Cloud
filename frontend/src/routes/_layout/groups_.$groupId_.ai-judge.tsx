/**
 * AI Judge Page - AI-powered rubric analysis and refinement
 */

import { useCallback, useState } from "react"
import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowLeft,
  Download,
  FileSpreadsheet,
  Plus,
  Sparkles,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { requireGroupManagerUser } from "@/features/auth/guards"
import {
  AiJudgeService,
  downloadBlob,
  rubricToContext,
  type ChatMessage,
  type RubricAnalysis,
  type RubricItem,
} from "@/features/ai-judge/api"
import {
  ChatPanel,
  RubricCard,
  RubricStats,
  RubricUploader,
} from "@/features/ai-judge/components"
import useCustomToast from "@/hooks/useCustomToast"

// ─── Route ────────────────────────────────────────────────────────────────────

export const Route = createFileRoute("/_layout/groups_/$groupId_/ai-judge")({
  component: AiJudgePage,
  beforeLoad: () => requireGroupManagerUser(),
  head: () => ({
    meta: [{ title: "AI 評分助手 - Campus Cloud" }],
  }),
})

// ─── Page ─────────────────────────────────────────────────────────────────────

function AiJudgePage() {
  const { groupId } = Route.useParams()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // State
  const [analysis, setAnalysis] = useState<RubricAnalysis | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [isChatting, setIsChatting] = useState(false)
  const [isExporting, setIsExporting] = useState(false)

  // Computed
  const items = analysis?.items ?? []
  const stats = {
    totalScore: items.reduce((sum, item) => sum + item.max_score, 0),
    autoCount: items.filter((item) => item.detectable === "auto").length,
    partialCount: items.filter((item) => item.detectable === "partial").length,
    manualCount: items.filter((item) => item.detectable === "manual").length,
  }

  // Handlers
  const handleUpload = useCallback(
    async (file: File) => {
      setIsUploading(true)
      try {
        const response = await AiJudgeService.uploadRubric(file)
        setAnalysis(response.analysis)
        setMessages([])
        showSuccessToast(
          `分析完成：${response.analysis.items.length} 個評分項目`,
        )
      } catch (err: any) {
        showErrorToast(err?.body?.detail ?? err?.message ?? "上傳失敗")
      } finally {
        setIsUploading(false)
      }
    },
    [showSuccessToast, showErrorToast],
  )

  const handleSendMessage = useCallback(
    async (content: string, isRefine = false) => {
      if (!analysis) return

      const userMessage: ChatMessage = { role: "user", content }
      const newMessages = [...messages, userMessage]
      setMessages(newMessages)
      setIsChatting(true)

      try {
        const response = await AiJudgeService.chat({
          messages: newMessages,
          rubric_context: rubricToContext(analysis),
          is_refine: isRefine,
        })

        // Add assistant reply
        const assistantMessage: ChatMessage = {
          role: "assistant",
          content: response.reply,
        }
        setMessages((prev) => [...prev, assistantMessage])

        // Update items if changed
        if (response.updated_items) {
          setAnalysis((prev) =>
            prev
              ? {
                  ...prev,
                  items: response.updated_items as RubricItem[],
                }
              : null,
          )
          showSuccessToast("評分表已更新")
        }
      } catch (err: any) {
        showErrorToast(err?.body?.detail ?? err?.message ?? "對話失敗")
        // Remove failed user message
        setMessages(messages)
      } finally {
        setIsChatting(false)
      }
    },
    [analysis, messages, showSuccessToast, showErrorToast],
  )

  const handleItemChange = useCallback(
    (index: number, updatedItem: RubricItem) => {
      if (!analysis) return
      const newItems = [...analysis.items]
      newItems[index] = updatedItem
      setAnalysis({ ...analysis, items: newItems })
    },
    [analysis],
  )

  const handleItemDelete = useCallback(
    (index: number) => {
      if (!analysis) return
      const newItems = analysis.items.filter((_, i) => i !== index)
      setAnalysis({ ...analysis, items: newItems })
    },
    [analysis],
  )

  const handleAddItem = useCallback(() => {
    if (!analysis) return
    const newItem: RubricItem = {
      id: `item-${Date.now()}`,
      title: "新評分項目",
      description: "",
      max_score: 10,
      detectable: "manual",
      detection_method: null,
      fallback: null,
    }
    setAnalysis({
      ...analysis,
      items: [...analysis.items, newItem],
    })
  }, [analysis])

  const handleExport = useCallback(async () => {
    if (!analysis) return

    setIsExporting(true)
    try {
      const blob = await AiJudgeService.downloadExcel({
        items: analysis.items,
        summary: analysis.summary,
      })
      downloadBlob(blob, "rubric.xlsx")
      showSuccessToast("Excel 下載成功")
    } catch (err: any) {
      showErrorToast(err?.message ?? "匯出失敗")
    } finally {
      setIsExporting(false)
    }
  }, [analysis, showSuccessToast, showErrorToast])

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to="/groups/$groupId"
            params={{ groupId }}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">AI 評分助手</h1>
            <p className="text-sm text-muted-foreground">
              上傳評分表，AI 自動分析可偵測性並協助優化
            </p>
          </div>
        </div>
        {analysis && (
          <Button onClick={handleExport} disabled={isExporting}>
            {isExporting ? (
              <>
                <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                匯出中...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                匯出 Excel
              </>
            )}
          </Button>
        )}
      </div>
      {/* Main content */}
      {!analysis ? (
        /* Upload section */
        (<Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5" />
              上傳評分表
            </CardTitle>
          </CardHeader>
          <CardContent>
            <RubricUploader onUpload={handleUpload} isLoading={isUploading} />
          </CardContent>
        </Card>)
      ) : (
        /* Analysis results */
        (<div className="grid gap-6 lg:grid-cols-[1fr_400px]">
          {/* Left: Rubric items */}
          <div className="space-y-4">
            {/* Stats */}
            <Card>
              <CardContent className="pt-6">
                <RubricStats {...stats} />
                {analysis.summary && (
                  <p className="mt-4 rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">
                    {analysis.summary}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Items */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>評分項目 ({items.length})</CardTitle>
                  <Button variant="outline" size="sm" onClick={handleAddItem}>
                    <Plus className="mr-1 h-4 w-4" />
                    新增項目
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {items.map((item, index) => (
                    <RubricCard
                      key={item.id}
                      item={item}
                      index={index}
                      onChange={(updated) => handleItemChange(index, updated)}
                      onDelete={() => handleItemDelete(index)}
                      disabled={isChatting}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
          {/* Right: Chat panel */}
          <Card className="flex h-[calc(100vh-200px)] flex-col lg:sticky lg:top-6">
            <CardHeader className="border-b">
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                AI 對話助手
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0">
              <ChatPanel
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isChatting}
                disabled={!analysis}
              />
            </CardContent>
          </Card>
        </div>)
      )}
    </div>
  )
}
