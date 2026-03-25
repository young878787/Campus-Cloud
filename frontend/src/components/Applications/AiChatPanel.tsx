import {
  Bot,
  Cpu,
  Download,
  FileText,
  Globe,
  HardDrive,
  Layers3,
  Loader2,
  MemoryStick,
  MessageSquare,
  Send,
  Sparkles,
  Trash2,
} from "lucide-react"
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
  type WheelEvent,
} from "react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface ChatMessage {
  role: "user" | "assistant" | "system"
  content: string
}

interface AiMetrics {
  total_tokens?: number
  elapsed_seconds?: number
  tokens_per_second?: number
}

interface FormPrefill {
  resource_type?: string
  hostname?: string
  service_template_slug?: string
  lxc_template_slug?: string
  lxc_os_image?: string
  vm_os_choice?: string
  vm_template_id?: number
  cores?: number
  memory_mb?: number
  disk_gb?: number
  username?: string
  reason?: string
}

export interface AiPlanResult {
  summary?: string
  final_plan?: {
    form_prefill?: FormPrefill
    recommended_templates?: Array<{
      slug: string
      name: string
      why: string
    }>
    machines?: Array<{
      name: string
      deployment_type: string
      cpu: number
      memory_mb: number
      disk_gb: number
      template_slug?: string
    }>
    application_target?: {
      service_name?: string
      execution_environment?: string
      environment_reason?: string
    }
  }
  ai_metrics?: AiMetrics
}

interface AiChatPanelProps {
  onImportPlan?: (prefill: FormPrefill) => void
  onImportReason?: (reason: string) => void
}

function getApiBase(): string {
  return (import.meta.env.VITE_API_URL || window.location.origin).replace(
    /\/$/,
    "",
  )
}

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token") || ""
  return token
    ? {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      }
    : { "Content-Type": "application/json" }
}

function stripThinkTags(text: string): string {
  const stripped = text.replace(/<think>[\s\S]*?<\/think>/gi, "").trim()
  return stripped || text.trim()
}

function renderMarkdown(source: string): string {
  let html = source
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")

  html = html.replace(
    /```([\s\S]*?)```/g,
    (_, code: string) =>
      `<pre class="my-2 p-3 rounded-lg bg-muted/80 overflow-auto text-xs"><code>${code.replace(/^\n+|\n+$/g, "")}</code></pre>`,
  )
  html = html.replace(
    /`([^`\n]+)`/g,
    '<code class="px-1 py-0.5 rounded bg-muted text-xs">$1</code>',
  )
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")

  html = html.replace(
    /^### (.+)$/gm,
    '<h4 class="font-semibold text-sm mt-3 mb-1">$1</h4>',
  )
  html = html.replace(
    /^## (.+)$/gm,
    '<h3 class="font-semibold text-base mt-3 mb-1">$1</h3>',
  )
  html = html.replace(
    /^# (.+)$/gm,
    '<h2 class="font-bold text-lg mt-3 mb-1">$1</h2>',
  )

  html = html.replace(
    /^[-*] (.+)$/gm,
    '<li class="ml-4 list-disc text-sm">$1</li>',
  )
  html = html.replace(
    /^\d+\. (.+)$/gm,
    '<li class="ml-4 list-decimal text-sm">$1</li>',
  )

  html = html.replace(/^---+$/gm, '<hr class="my-2 border-border/50" />')

  html = html.replace(/\n{2,}/g, "</p><p>")
  html = html.replace(/\n/g, "<br />")

  return `<p>${html}</p>`
}

function renderPlanMarkdown(source: string): string {
  return renderMarkdown(source || "").replace(
    /<p>/g,
    '<p class="text-sm leading-6">',
  )
}

export function AiChatPanel({
  onImportPlan,
  onImportReason,
}: AiChatPanelProps) {
  const { t } = useTranslation("applications")
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationHistory, setConversationHistory] = useState<ChatMessage[]>(
    [],
  )
  const [planContextMessage, setPlanContextMessage] =
    useState<ChatMessage | null>(null)
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [latestPlan, setLatestPlan] = useState<AiPlanResult | null>(null)
  const [metrics, setMetrics] = useState<AiMetrics | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      }
    })
  }, [])

  useEffect(() => {
    void messages
    void isLoading
    scrollToBottom()
  }, [messages, isLoading, scrollToBottom])

  useEffect(() => {
    void input
    if (!inputRef.current) return
    inputRef.current.style.height = "0px"
    inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 220)}px`
  }, [input])

  const buildRequestMessages = useCallback(
    (history: ChatMessage[]) =>
      planContextMessage ? [...history, planContextMessage] : history,
    [planContextMessage],
  )

  const sendChat = async () => {
    const text = input.trim()
    if (!text || isLoading) return

    setInput("")
    const userMsg: ChatMessage = { role: "user", content: text }
    setMessages((prev) => [...prev, userMsg])

    const newHistory = [...conversationHistory, userMsg]
    setConversationHistory(newHistory)
    setIsLoading(true)

    try {
      const requestMessages = buildRequestMessages(newHistory)
      const res = await fetch(
        `${getApiBase()}/api/v1/ai/template-recommendation/chat`,
        {
          method: "POST",
          headers: getAuthHeaders(),
          body: JSON.stringify({
            messages: requestMessages,
            top_k: 5,
            device_nodes: [],
          }),
        },
      )
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const reply = stripThinkTags(data.reply || "")

      const aiMsg: ChatMessage = { role: "assistant", content: reply }
      setMessages((prev) => [...prev, aiMsg])
      setConversationHistory((prev) => [...prev, aiMsg])
      setMetrics({
        total_tokens: data.total_tokens,
        elapsed_seconds: data.elapsed_seconds,
        tokens_per_second: data.tokens_per_second,
      })
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `[${t("aiChat.chatError")}] ${err instanceof Error ? err.message : String(err)}`,
        },
      ])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  const generatePlan = async () => {
    if (conversationHistory.length === 0) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: t("aiChat.needChatFirst"),
        },
      ])
      return
    }

    setIsLoading(true)
    try {
      const requestMessages = buildRequestMessages(conversationHistory)
      const res = await fetch(
        `${getApiBase()}/api/v1/ai/template-recommendation/recommend`,
        {
          method: "POST",
          headers: getAuthHeaders(),
          body: JSON.stringify({
            messages: requestMessages,
            top_k: 5,
            device_nodes: [],
          }),
        },
      )
      if (!res.ok) throw new Error(await res.text())
      const data: AiPlanResult = await res.json()
      setLatestPlan(data)
      if (data.ai_metrics) setMetrics(data.ai_metrics)

      const planContext = [
        data.summary?.trim(),
        data.final_plan?.application_target?.environment_reason?.trim(),
        data.final_plan?.form_prefill?.reason?.trim(),
      ]
        .filter(Boolean)
        .join("\n\n")

      if (planContext) {
        setPlanContextMessage({
          role: "assistant",
          content: `AI 已產生推薦配置，以下是目前方案摘要：\n${planContext}`,
        })
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `[${t("aiChat.planError")}] ${err instanceof Error ? err.message : String(err)}`,
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleImportPlan = () => {
    if (!latestPlan?.final_plan?.form_prefill || !onImportPlan) return
    onImportPlan(latestPlan.final_plan.form_prefill)
  }

  const handleImportReason = () => {
    if (!onImportReason) return
    const reason =
      latestPlan?.final_plan?.form_prefill?.reason || latestPlan?.summary || ""
    if (reason) onImportReason(reason)
  }

  const clearChat = () => {
    setMessages([])
    setConversationHistory([])
    setPlanContextMessage(null)
    setLatestPlan(null)
    setMetrics(null)
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendChat()
    }
  }

  const handleMessagesWheel = useCallback(
    (event: WheelEvent<HTMLDivElement>) => {
      const container = scrollRef.current
      if (!container) return

      const maxScrollTop = container.scrollHeight - container.clientHeight
      if (maxScrollTop <= 0) return

      const scrollingDown = event.deltaY > 0
      const scrollingUp = event.deltaY < 0
      const canScrollDown = container.scrollTop < maxScrollTop
      const canScrollUp = container.scrollTop > 0

      if ((scrollingDown && canScrollDown) || (scrollingUp && canScrollUp)) {
        event.preventDefault()
        container.scrollTop += event.deltaY * 0.45
      }
    },
    [],
  )

  const plan = latestPlan?.final_plan
  const formPrefill = plan?.form_prefill
  const resourceType =
    String(formPrefill?.resource_type || "lxc").toLowerCase() === "vm"
      ? "vm"
      : "lxc"
  const templateLabel =
    resourceType === "vm"
      ? formPrefill?.vm_os_choice || formPrefill?.vm_template_id || "-"
      : formPrefill?.service_template_slug ||
        formPrefill?.lxc_template_slug ||
        "-"

  const summaryReason =
    formPrefill?.reason || latestPlan?.summary || t("aiChat.planError")
  const inputLength = input.length

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 pb-3">
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-4 w-4 text-primary" />
          </div>
          <h3 className="text-sm font-semibold">{t("aiChat.title")}</h3>
        </div>
        {metrics && (
          <Badge variant="outline" className="text-[10px] font-mono">
            {t("aiChat.tokens", {
              count: metrics.total_tokens || 0,
            })}
            {metrics.tokens_per_second
              ? ` | ${metrics.tokens_per_second.toFixed(1)} tok/s`
              : ""}
          </Badge>
        )}
      </div>

      <div
        ref={scrollRef}
        onWheel={handleMessagesWheel}
        className="hidden-scroll min-h-0 flex-1 overflow-y-auto rounded-xl border border-border/60 bg-background/40 p-2"
      >
        <div className="flex flex-col gap-2.5 p-2.5">
          {messages.length === 0 && (
            <div className="animate-in fade-in flex gap-2.5 duration-300">
              <div className="flex max-w-[90%] items-start gap-2.5">
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Sparkles className="h-3 w-3 text-primary" />
                </div>
                <div className="rounded-xl rounded-tl-sm border border-border/60 bg-card/80 px-3 py-2 text-sm leading-relaxed">
                  {t("aiChat.systemGreeting")}
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, i) => {
            const isUser = msg.role === "user"
            return (
              <div
                key={`msg-${i}-${msg.role}`}
                className={`animate-in fade-in slide-in-from-bottom-2 flex gap-2.5 duration-200 ${
                  isUser ? "justify-end" : "justify-start"
                }`}
              >
                {!isUser && (
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
                    <Bot className="h-3 w-3 text-primary" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                    isUser
                      ? "rounded-tr-sm bg-primary text-primary-foreground"
                      : "rounded-tl-sm border border-border/60 bg-card/80"
                  }`}
                >
                  {isUser ? (
                    <span className="whitespace-pre-wrap">{msg.content}</span>
                  ) : (
                    <div
                      className="prose prose-sm max-w-none dark:prose-invert [&_li]:my-0.5 [&_p]:mb-1.5 [&_p:last-child]:mb-0"
                      // biome-ignore lint/security/noDangerouslySetInnerHtml: controlled markdown
                      dangerouslySetInnerHTML={{
                        __html: renderMarkdown(msg.content),
                      }}
                    />
                  )}
                </div>
                {isUser && (
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary">
                    <MessageSquare className="h-3 w-3 text-primary-foreground" />
                  </div>
                )}
              </div>
            )
          })}

          {isLoading && (
            <div className="animate-in fade-in flex gap-2.5 duration-200">
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
                <Bot className="h-3 w-3 text-primary" />
              </div>
              <div className="rounded-xl rounded-tl-sm border border-border/60 bg-card/80 px-3 py-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t("aiChat.loading")}
                </div>
              </div>
            </div>
          )}

          {latestPlan && plan && (
            <div className="animate-in fade-in slide-in-from-bottom-2 flex gap-2.5 duration-300">
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
                <Bot className="h-3 w-3 text-primary" />
              </div>
              <div className="min-w-0 max-w-[90%] overflow-hidden rounded-xl rounded-tl-sm border border-border/60 bg-card/90">
                <div className="border-b bg-primary/5 px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                        <Layers3 className="h-4 w-4 text-primary" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold">
                          {t("aiChat.planTitle")}
                        </div>
                        <div className="truncate text-xs text-muted-foreground">
                          {plan.application_target?.service_name ||
                            "AI 推薦方案"}
                        </div>
                      </div>
                    </div>
                    <Badge variant="secondary" className="shrink-0 uppercase">
                      {resourceType}
                    </Badge>
                  </div>
                </div>

                <div className="space-y-4 p-4">
                  <div
                    className="rounded-xl border border-primary/10 bg-primary/5 px-3.5 py-3"
                    // biome-ignore lint/security/noDangerouslySetInnerHtml: controlled markdown
                    dangerouslySetInnerHTML={{
                      __html: renderPlanMarkdown(
                        latestPlan.summary ||
                          "AI generated a recommendation summary.",
                      ),
                    }}
                  />

                  <div className="space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      服務定位
                    </div>
                    <div className="rounded-xl border border-border/60 bg-muted/10 px-3.5 py-3">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge variant="outline">
                          {plan.application_target?.execution_environment ||
                            resourceType.toUpperCase()}
                        </Badge>
                        {plan.application_target?.service_name && (
                          <span className="text-sm font-semibold">
                            {plan.application_target.service_name}
                          </span>
                        )}
                      </div>
                      <div
                        className="text-sm text-muted-foreground [&_p]:mb-1.5 [&_p:last-child]:mb-0"
                        // biome-ignore lint/security/noDangerouslySetInnerHtml: controlled markdown
                        dangerouslySetInnerHTML={{
                          __html: renderPlanMarkdown(
                            plan.application_target?.environment_reason ||
                              "This is the environment recommended by AI.",
                          ),
                        }}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      表單預填欄位
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="rounded-xl border border-border/60 bg-muted/10 p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <Layers3 className="h-3.5 w-3.5" />
                          資源類型
                        </div>
                        <div className="text-sm font-semibold uppercase">
                          {formPrefill?.resource_type || "-"}
                        </div>
                      </div>
                      <div className="rounded-xl border border-border/60 bg-muted/10 p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <Globe className="h-3.5 w-3.5" />
                          Hostname
                        </div>
                        <div className="break-all text-sm font-semibold">
                          {formPrefill?.hostname || "-"}
                        </div>
                      </div>
                      <div className="rounded-xl border border-border/60 bg-muted/10 p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <FileText className="h-3.5 w-3.5" />
                          {resourceType === "vm"
                            ? "VM Template"
                            : "Service Template"}
                        </div>
                        <div className="break-all text-sm font-semibold">
                          {String(templateLabel)}
                        </div>
                      </div>
                      <div className="rounded-xl border border-border/60 bg-muted/10 p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <Cpu className="h-3.5 w-3.5" />
                          CPU / RAM / Disk
                        </div>
                        <div className="space-y-1 text-sm font-semibold">
                          <div className="flex items-center gap-2">
                            <Cpu className="h-3.5 w-3.5 text-primary" />
                            {formPrefill?.cores || "-"} cores
                          </div>
                          <div className="flex items-center gap-2">
                            <MemoryStick className="h-3.5 w-3.5 text-primary" />
                            {formPrefill?.memory_mb || "-"} MB
                          </div>
                          <div className="flex items-center gap-2">
                            <HardDrive className="h-3.5 w-3.5 text-primary" />
                            {formPrefill?.disk_gb || "-"} GB
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {plan.recommended_templates &&
                    plan.recommended_templates.length > 0 && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          推薦模板
                        </div>
                        <div className="space-y-3">
                          {plan.recommended_templates
                            .slice(0, 3)
                            .map((template) => (
                              <div
                                key={template.slug}
                                className="rounded-xl border border-border/60 bg-muted/10 px-3.5 py-3"
                              >
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <div className="text-sm font-semibold">
                                    {template.name}
                                  </div>
                                  <Badge variant="outline">
                                    {template.slug}
                                  </Badge>
                                </div>
                                <div
                                  className="text-sm text-muted-foreground [&_p]:mb-1.5 [&_p:last-child]:mb-0"
                                  // biome-ignore lint/security/noDangerouslySetInnerHtml: controlled markdown
                                  dangerouslySetInnerHTML={{
                                    __html: renderPlanMarkdown(template.why),
                                  }}
                                />
                              </div>
                            ))}
                        </div>
                      </div>
                    )}

                  <div className="space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      申請原因
                    </div>
                    <div
                      className="rounded-xl border border-border/60 bg-muted/10 px-3.5 py-3 text-sm text-muted-foreground [&_p]:mb-1.5 [&_p:last-child]:mb-0"
                      // biome-ignore lint/security/noDangerouslySetInnerHtml: controlled markdown
                      dangerouslySetInnerHTML={{
                        __html: renderPlanMarkdown(summaryReason),
                      }}
                    />
                  </div>

                  <div className="border-t pt-4">
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <Button
                        size="sm"
                        className="h-9"
                        onClick={handleImportPlan}
                      >
                        <Download className="mr-1.5 h-3 w-3" />
                        {t("aiChat.importPlan")}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="h-9"
                        onClick={handleImportReason}
                      >
                        <FileText className="mr-1.5 h-3 w-3" />
                        {t("aiChat.importReason")}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mb-1 shrink-0 rounded-xl border border-border/60 bg-background/70 p-3">
        <Textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("aiChat.placeholder")}
          className="min-h-[88px] max-h-[220px] resize-none border-0 bg-transparent px-0 py-1 text-sm shadow-none focus-visible:ring-0"
          disabled={isLoading}
        />
        <div className="flex items-center justify-between gap-3 border-t border-border/50 px-0 pb-1 pt-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="h-8 px-2 text-xs text-muted-foreground"
              onClick={clearChat}
              disabled={isLoading}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="h-8 rounded-full px-3 text-xs"
              onClick={generatePlan}
              disabled={isLoading || conversationHistory.length === 0}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              {t("aiChat.generatePlan")}
            </Button>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-[11px] text-muted-foreground">
              {inputLength}
            </span>
            <Button
              size="icon"
              className="h-8 w-8 rounded-full"
              onClick={sendChat}
              disabled={isLoading || !input.trim()}
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
