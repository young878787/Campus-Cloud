import { FormEvent, useMemo, useState } from "react"
import { Bot, MessageSquare, Send, Wrench } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import {
  AiPveLogService,
  type ToolCallRecord,
} from "@/features/ai-pve-log/api"
import useCustomToast from "@/hooks/useCustomToast"

type LocalMessage = {
  role: "user" | "assistant"
  content: string
  tools?: ToolCallRecord[]
}

/**
 * AI PVE Message Content Block - extracted from Page
 */
export function AiPveMessageContent({ groupId: _groupId }: { groupId: string }) {
  const { showErrorToast } = useCustomToast()

  const [input, setInput] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [messages, setMessages] = useState<LocalMessage[]>([
    {
      role: "assistant",
      content:
        "我是 AI-PVE 助手。你可以詢問節點資源、VM/LXC 狀態、儲存空間使用率等資訊。",
    },
  ])

  const canSend = useMemo(
    () => input.trim().length > 0 && !isSending,
    [input, isSending],
  )

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const message = input.trim()
    if (!message || isSending) return

    setInput("")
    setIsSending(true)
    setMessages((prev) => [...prev, { role: "user", content: message }])

    try {
      const response = await AiPveLogService.chat({ message })
      if (response.error) {
        showErrorToast(response.error)
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.reply || response.error || "AI-PVE 沒有回傳內容",
          tools: response.tools_called,
        },
      ])
    } catch (err: any) {
      const detail = err?.body?.detail ?? err?.message ?? "AI-PVE 對話失敗"
      showErrorToast(detail)
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `發生錯誤：${detail}`,
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">AI-PVE 訊息</h2>
          <p className="text-sm text-muted-foreground mt-1">
            針對當前 PVE 環境快速提問，取得 VM/LXC 與節點運行建議
          </p>
        </div>
      </div>

      <Card className="flex h-[calc(100vh-200px)] min-h-[500px] flex-col shadow-sm border-border/50">
        <CardHeader className="border-b bg-muted/10 py-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageSquare className="h-5 w-5" />
            對話記錄
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
          <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-border/50 bg-muted/10 p-4 shadow-inner">
            {messages.map((msg, index) => (
              <div
                key={`${msg.role}-${index}`}
                className={`rounded-xl p-4 text-sm ${
                  msg.role === "user"
                    ? "ml-8 bg-primary/10 border border-primary/20"
                    : "mr-8 border bg-background shadow-sm"
                }`}
              >
                <div className="mb-2 flex items-center gap-2 font-medium">
                  {msg.role === "assistant" ? (
                    <Bot className="h-4 w-4 text-primary" />
                  ) : (
                    <MessageSquare className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className={msg.role === "assistant" ? "text-primary" : "text-muted-foreground"}>
                    {msg.role === "assistant" ? "AI-PVE" : "你"}
                  </span>
                </div>
                <p className="whitespace-pre-wrap leading-relaxed text-foreground/90">{msg.content}</p>
                {msg.tools && msg.tools.length > 0 && (
                  <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
                    <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
                      <Wrench className="h-3.5 w-3.5" />
                      系統呼叫：
                    </span>
                    {msg.tools.map((tool, toolIndex) => (
                      <Badge key={`${tool.name}-${toolIndex}`} variant="secondary" className="bg-muted text-[10px] uppercase">
                        {tool.name}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {isSending && (
              <div className="mr-8 rounded-xl border bg-background shadow-sm p-4 text-sm text-muted-foreground flex items-center gap-3">
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                </span>
                AI-PVE 思考中...
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="例如：幫我列出目前 CPU 使用率最高的 5 台 VM，並附上節點名稱"
              className="min-h-[100px] resize-none focus-visible:ring-1"
              disabled={isSending}
            />
            <div className="flex justify-end">
              <Button type="submit" disabled={!canSend} className="w-full sm:w-auto">
                <Send className="mr-2 h-4 w-4" />
                發送訊息
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
