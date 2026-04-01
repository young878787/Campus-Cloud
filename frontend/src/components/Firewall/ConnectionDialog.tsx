import { Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

// PVE 支援的所有協定
const PVE_PROTOCOLS = [
  { value: "tcp", label: "TCP", hasPort: true },
  { value: "udp", label: "UDP", hasPort: true },
  { value: "sctp", label: "SCTP", hasPort: true },
  { value: "dccp", label: "DCCP", hasPort: true },
  { value: "udplite", label: "UDPLite", hasPort: true },
  { value: "icmp", label: "ICMP", hasPort: false },
  { value: "icmpv6", label: "ICMPv6", hasPort: false },
  { value: "igmp", label: "IGMP", hasPort: false },
  { value: "esp", label: "ESP", hasPort: false },
  { value: "ah", label: "AH", hasPort: false },
  { value: "gre", label: "GRE", hasPort: false },
  { value: "ospf", label: "OSPF", hasPort: false },
  { value: "vrrp", label: "VRRP", hasPort: false },
] as const

const PROTOCOLS_WITH_PORT = new Set(
  PVE_PROTOCOLS.filter((p) => p.hasPort).map((p) => p.value),
)

type PortSpec = {
  port: number
  protocol: string
}

type Props = {
  open: boolean
  sourceVmid: number | null // null = Internet
  sourceName: string
  targetVmid: number | null
  targetName: string
  onConfirm: (ports: PortSpec[], direction: "one_way" | "bidirectional") => void
  onClose: () => void
}

export function ConnectionDialog({
  open,
  sourceVmid,
  sourceName,
  targetName,
  targetVmid,
  onConfirm,
  onClose,
}: Props) {
  const [ports, setPorts] = useState<PortSpec[]>([
    { port: 80, protocol: "tcp" },
  ])
  const [direction, setDirection] = useState<"one_way" | "bidirectional">(
    "one_way",
  )

  const isGateway = targetVmid === null
  const isInbound = sourceVmid === null // Internet → VM 入站

  const addPort = () => {
    setPorts([...ports, { port: 443, protocol: "tcp" }])
  }

  const removePort = (index: number) => {
    setPorts(ports.filter((_, i) => i !== index))
  }

  const updatePort = (
    index: number,
    field: "port" | "protocol",
    value: string | number,
  ) => {
    const updated = [...ports]
    updated[index] = { ...updated[index], [field]: value }
    setPorts(updated)
  }

  const handleConfirm = () => {
    const validPorts = ports
      .filter((p) => {
        if (PROTOCOLS_WITH_PORT.has(p.protocol)) {
          return p.port >= 1 && p.port <= 65535
        }
        return true // 無端口協定直接通過
      })
      .map((p) => ({
        // 無端口協定統一 port=0 傳給後端
        port: PROTOCOLS_WITH_PORT.has(p.protocol) ? p.port : 0,
        protocol: p.protocol,
      }))
    if (validPorts.length === 0) {
      toast.error("請輸入有效的設定")
      return
    }
    onConfirm(validPorts, direction)
    // 重置狀態
    setPorts([{ port: 80, protocol: "tcp" }])
    setDirection("one_way")
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-[#1a1a1a] border-[#2e2e2e] text-gray-100 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-gray-100">設定連線規則</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* 連線方向說明 */}
          <div className="text-sm text-gray-400 bg-[#111] rounded-lg p-3 border border-[#2e2e2e]">
            {isInbound ? (
              <>
                <span className="text-blue-400 font-medium">Internet</span>
                <span className="text-gray-500"> → </span>
                <span className="text-blue-400 font-medium">{targetName}</span>
                <span className="text-gray-400">（入站開放）</span>
              </>
            ) : (
              <>
                <span className="text-emerald-400 font-medium">
                  {sourceName}
                </span>
                {isGateway ? (
                  <span className="text-gray-400">
                    {" "}
                    → 連到 Internet（上網）
                  </span>
                ) : (
                  <>
                    <span className="text-gray-500"> → </span>
                    <span className="text-emerald-400 font-medium">
                      {targetName}
                    </span>
                  </>
                )}
              </>
            )}
          </div>

          {/* 端口設定 */}
          <div className="space-y-2">
            <Label className="text-gray-300 text-sm">允許端口</Label>
            {ports.map((port, index) => (
              <div key={index} className="flex items-center gap-2">
                {PROTOCOLS_WITH_PORT.has(port.protocol) ? (
                  <Input
                    type="number"
                    min={1}
                    max={65535}
                    value={port.port}
                    onChange={(e) =>
                      updatePort(
                        index,
                        "port",
                        parseInt(e.target.value, 10) || 80,
                      )
                    }
                    className="bg-[#111] border-[#2e2e2e] text-gray-100 w-24 h-8 text-sm"
                    placeholder="80"
                  />
                ) : (
                  <div className="w-24 h-8 flex items-center px-2 text-xs text-gray-500 bg-[#111] border border-[#2e2e2e] rounded-md">
                    無端口
                  </div>
                )}
                <Select
                  value={port.protocol}
                  onValueChange={(v) => updatePort(index, "protocol", v)}
                >
                  <SelectTrigger className="bg-[#111] border-[#2e2e2e] text-gray-100 w-24 h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a1a1a] border-[#2e2e2e] text-gray-100">
                    {PVE_PROTOCOLS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {ports.length > 1 && (
                  <button
                    onClick={() => removePort(index)}
                    className="p-1 hover:text-red-400 text-gray-500 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
            <button
              onClick={addPort}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
            >
              <Plus className="w-3 h-3" />
              新增端口
            </button>
          </div>

          {/* 方向設定（VM 間連線才顯示，入站連線永遠單向） */}
          {!isGateway && !isInbound && (
            <div className="space-y-2">
              <Label className="text-gray-300 text-sm">連線方向</Label>
              <div className="flex gap-2">
                {(["one_way", "bidirectional"] as const).map((dir) => (
                  <button
                    key={dir}
                    onClick={() => setDirection(dir)}
                    className={`
                      px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                      ${
                        direction === dir
                          ? "bg-emerald-900/50 border border-emerald-600 text-emerald-400"
                          : "bg-[#111] border border-[#2e2e2e] text-gray-400 hover:border-[#3e3e3e]"
                      }
                    `}
                  >
                    {dir === "one_way" ? "→ 單向" : "↔ 雙向"}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="ghost"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-100"
          >
            取消
          </Button>
          <Button
            onClick={handleConfirm}
            className="bg-emerald-700 hover:bg-emerald-600 text-white"
          >
            建立連線
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
