import { Handle, type Node, type NodeProps, Position } from "@xyflow/react"
import { Server, Shield, ShieldOff } from "lucide-react"

export type VMNodeData = {
  vmid: number
  name: string
  status: string
  ip_address: string | null
  firewall_enabled: boolean
}

type VMNodeType = Node<VMNodeData, "vm">

export function VMNode({ data, selected }: NodeProps<VMNodeType>) {
  const isRunning = data.status === "running"
  const hasIp = !!data.ip_address

  return (
    <div
      className={`
        relative flex items-center gap-3 px-4 py-3
        bg-card border rounded-xl cursor-pointer
        transition-all duration-200 min-w-[180px]
        ${
          selected
            ? "border-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.4)]"
            : "border-border hover:border-ring/50"
        }
      `}
    >
      {/* 左側 icon */}
      <div className="flex-shrink-0 w-8 h-8 bg-muted rounded-lg flex items-center justify-center">
        <Server className="w-4 h-4 text-muted-foreground" />
      </div>

      {/* 主要資訊 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {/* 狀態指示點 */}
          <span
            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              isRunning ? "bg-emerald-400" : "bg-red-400"
            }`}
          />
          <span className="text-sm font-medium text-foreground truncate">
            {data.name}
          </span>
        </div>
        <div className="text-xs text-muted-foreground mt-0.5 truncate">
          {hasIp ? data.ip_address : `VMID: ${data.vmid}`}
        </div>
      </div>

      {/* 防火牆狀態圖示 */}
      <div
        className="flex-shrink-0"
        title={data.firewall_enabled ? "防火牆已啟用" : "防火牆未啟用"}
      >
        {data.firewall_enabled ? (
          <Shield className="w-3.5 h-3.5 text-emerald-400" />
        ) : (
          <ShieldOff className="w-3.5 h-3.5 text-red-400" />
        )}
      </div>

      {/* VM→Internet 出站 handle（右側，綠色）*/}
      <Handle
        id="out-internet"
        type="source"
        position={Position.Right}
        className="!w-2.5 !h-2.5 !bg-emerald-400 !border-2 !border-card"
      />
      {/* Internet→VM 入站 handle（左側，藍色）*/}
      <Handle
        id="in-internet"
        type="target"
        position={Position.Left}
        className="!w-2.5 !h-2.5 !bg-blue-400 !border-2 !border-card"
      />
      {/* VM→VM 出站 handle（底部，橘色）*/}
      <Handle
        id="out-vm"
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !bg-orange-400 !border-2 !border-card"
      />
      {/* VM→VM 入站 handle（頂部，橘色）*/}
      <Handle
        id="in-vm"
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-orange-400 !border-2 !border-card"
      />
    </div>
  )
}
