import {
  Background,
  BackgroundVariant,
  type Connection,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, EyeOff, LayoutGrid, RefreshCw, Shield } from "lucide-react"
import type React from "react"
import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { FirewallService } from "@/services/firewall"
import { ConnectionDialog } from "./ConnectionDialog"
import type { ConnectionEdgeData } from "./ConnectionEdge"
import { ConnectionEdge } from "./ConnectionEdge"
import { DeleteGatewayWarning } from "./DeleteGatewayWarning"
import type { GatewayNodeData } from "./GatewayNode"
import { GatewayNode } from "./GatewayNode"
import { RulesPanel } from "./RulesPanel"
import type { VMNodeData } from "./VMNode"
import { VMNode } from "./VMNode"

// 自訂節點和邊類型
const nodeTypes = {
  vm: VMNode,
  gateway: GatewayNode,
}

const edgeTypes = {
  connection: ConnectionEdge,
}

type PendingConnection = {
  sourceVmid: number | null
  sourceName: string
  targetVmid: number | null
  targetName: string
}

function FirewallTopologyInner() {
  const queryClient = useQueryClient()
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  const [pendingConnection, setPendingConnection] =
    useState<PendingConnection | null>(null)
  const [gatewayWarning, setGatewayWarning] = useState<{
    vmid: number
    vmName: string
  } | null>(null)
  const [selectedVmid, setSelectedVmid] = useState<number | null>(null)
  const [selectedVmName, setSelectedVmName] = useState("")

  // ─── 標籤開關 & 節點聚焦 ──────────────────────────────────────────────────
  const [showLabels, setShowLabels] = useState(false)
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null)
  const edgesRef = useRef<Edge[]>([])

  // 同步 edgesRef
  useEffect(() => {
    edgesRef.current = edges
  }, [edges])

  const layoutSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { fitView } = useReactFlow()

  useEffect(() => {
    return () => {
      if (layoutSaveTimer.current) clearTimeout(layoutSaveTimer.current)
    }
  }, [])

  // ─── 聚焦模式：計算關聯節點並套用透明度 ─────────────────────────────────

  useEffect(() => {
    if (focusedNodeId === null) {
      // 清除聚焦：所有節點恢復正常，邊套用 showLabels
      setNodes((prev) =>
        prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })),
      )
      setEdges((prev) =>
        prev.map((e) => ({
          ...e,
          data: {
            ...e.data,
            showLabels,
            isHighlighted: false,
            hidden: false,
          } as ConnectionEdgeData,
        })),
      )
      return
    }

    // 找出與聚焦節點相連的邊和節點 id
    const connectedEdgeIds = new Set<string>()
    const connectedNodeIds = new Set<string>([focusedNodeId])

    for (const e of edgesRef.current) {
      if (e.source === focusedNodeId || e.target === focusedNodeId) {
        connectedEdgeIds.add(e.id)
        connectedNodeIds.add(e.source)
        connectedNodeIds.add(e.target)
      }
    }

    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        style: {
          ...n.style,
          opacity: connectedNodeIds.has(n.id) ? 1 : 0.12,
        },
      })),
    )

    setEdges((prev) =>
      prev.map((e) => {
        const isConnected = connectedEdgeIds.has(e.id)
        return {
          ...e,
          data: {
            ...e.data,
            showLabels,
            isHighlighted: isConnected,
            hidden: !isConnected,
          } as ConnectionEdgeData,
        }
      }),
    )
  }, [focusedNodeId, showLabels, setEdges, setNodes])

  // ─── showLabels 變更時更新所有邊的 data ──────────────────────────────────

  useEffect(() => {
    if (focusedNodeId !== null) return // 聚焦模式由上面的 effect 處理
    setEdges((prev) =>
      prev.map((e) => ({
        ...e,
        data: {
          ...e.data,
          showLabels,
        } as ConnectionEdgeData,
      })),
    )
  }, [showLabels, focusedNodeId, setEdges])

  // ─── 載入拓撲 ─────────────────────────────────────────────────────────────

  const {
    data: topology,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["firewall-topology"],
    queryFn: () => FirewallService.getFirewallTopology(),
    staleTime: 30_000,
  })

  // ─── 刪除連線 ─────────────────────────────────────────────────────────────

  const deleteConnectionMutation = useMutation({
    mutationFn: ({
      sourceVmid,
      targetVmid,
    }: {
      sourceVmid: number | null
      targetVmid: number | null
    }) =>
      FirewallService.deleteFirewallConnection({
        requestBody: {
          source_vmid: sourceVmid as number,
          target_vmid: targetVmid,
        },
      }),
    onSuccess: () => {
      toast.success("連線已刪除")
      queryClient.invalidateQueries({ queryKey: ["firewall-topology"] })
    },
    onError: (e: Error) => {
      toast.error(`刪除連線失敗: ${e.message}`)
    },
  })

  const handleDeleteConnection = useCallback(
    (sourceVmid: number | null, targetVmid: number | null) => {
      if (targetVmid === null && sourceVmid !== null) {
        // 刪除往網關的連線 → 顯示警告
        const vmName =
          topology?.nodes.find((n) => n.vmid === sourceVmid)?.name ??
          `VM-${sourceVmid}`
        setGatewayWarning({ vmid: sourceVmid, vmName })
      } else {
        deleteConnectionMutation.mutate({ sourceVmid, targetVmid })
      }
    },
    [topology, deleteConnectionMutation],
  )

  // 用 ref 穩定 handleDeleteConnection 引用，避免 useEffect 無限迴圈
  const handleDeleteConnectionRef = useRef(handleDeleteConnection)
  handleDeleteConnectionRef.current = handleDeleteConnection

  // 將 topology 資料轉換為 React Flow 格式
  useEffect(() => {
    if (!topology) return

    const rfNodes: Node[] = topology.nodes.map((n) => ({
      id: n.vmid !== null ? `vm-${n.vmid}` : "gateway",
      type: n.node_type === "gateway" ? "gateway" : "vm",
      position: { x: n.position_x, y: n.position_y },
      data:
        n.node_type === "gateway"
          ? ({ name: n.name } satisfies GatewayNodeData)
          : ({
              vmid: n.vmid!,
              name: n.name,
              status: n.status ?? "unknown",
              ip_address: n.ip_address ?? null,
              firewall_enabled: n.firewall_enabled,
            } satisfies VMNodeData),
    }))

    const rfEdges: Edge[] = topology.edges.map((e, i) => {
      const srcId = e.source_vmid !== null ? `vm-${e.source_vmid}` : "gateway"
      const tgtId = e.target_vmid !== null ? `vm-${e.target_vmid}` : "gateway"
      const isGateway = e.source_vmid !== null && e.target_vmid === null // VM→internet 出站
      const isInbound = e.source_vmid === null && e.target_vmid !== null // internet→VM 入站
      const isVMtoVM = e.source_vmid !== null && e.target_vmid !== null // VM→VM

      // 依連線類型選擇對應 handle，確保線路不交叉
      const sourceHandle = isGateway
        ? "out-internet"
        : isInbound
          ? "out"
          : "out-vm"
      const targetHandle = isGateway
        ? "in"
        : isInbound
          ? "in-internet"
          : "in-vm"

      return {
        id: `edge-${i}`,
        source: srcId,
        target: tgtId,
        sourceHandle,
        targetHandle,
        type: "connection",
        animated: false,
        data: {
          ports: e.ports ?? [],
          direction: e.direction ?? "one_way",
          isGateway,
          isInbound,
          isVMtoVM,
          sourceVmid: e.source_vmid,
          targetVmid: e.target_vmid,
          showLabels,
          isHighlighted: false,
          onDelete: (...args: Parameters<typeof handleDeleteConnection>) =>
            handleDeleteConnectionRef.current(...args),
        } satisfies ConnectionEdgeData,
      }
    })

    setNodes(rfNodes)
    setEdges(rfEdges)
    // 重新載入後清除聚焦
    setFocusedNodeId(null)
  }, [topology, setEdges, setNodes, showLabels])

  // ─── 儲存佈局（debounce 500ms）────────────────────────────────────────────

  const saveLayoutMutation = useMutation({
    mutationFn: (nodes: Node[]) => {
      const layoutNodes = nodes.map((n) => ({
        vmid: n.id === "gateway" ? null : parseInt(n.id.replace("vm-", ""), 10),
        node_type: (n.id === "gateway" ? "gateway" : "vm") as "vm" | "gateway",
        position_x: n.position.x,
        position_y: n.position.y,
      }))
      return FirewallService.saveFirewallLayout({
        requestBody: { nodes: layoutNodes },
      })
    },
  })

  // ─── 自動排列 ──────────────────────────────────────────────────────────────

  const autoArrange = useCallback(() => {
    setNodes((prev) => {
      const vmNodes = prev.filter((n) => n.type === "vm")
      const gatewayNode = prev.find((n) => n.type === "gateway")

      const VM_COL_X = 160
      const ROW_H = 160
      const GATEWAY_X = VM_COL_X + 520

      const totalH = vmNodes.length * ROW_H
      const startY = 80

      const arranged: Node[] = vmNodes.map((node, i) => ({
        ...node,
        position: { x: VM_COL_X, y: startY + i * ROW_H },
      }))

      if (gatewayNode) {
        arranged.push({
          ...gatewayNode,
          position: { x: GATEWAY_X, y: startY + (totalH - ROW_H) / 2 },
        })
      }

      // 儲存排列後的佈局
      setTimeout(() => {
        saveLayoutMutation.mutate(arranged)
        fitView({ padding: 0.2, duration: 400 })
      }, 50)

      return arranged
    })
  }, [setNodes, saveLayoutMutation, fitView])

  const onNodeDragStop = useCallback(
    (_event: React.MouseEvent, _node: Node, currentNodes: Node[]) => {
      if (layoutSaveTimer.current) clearTimeout(layoutSaveTimer.current)
      layoutSaveTimer.current = setTimeout(() => {
        saveLayoutMutation.mutate(currentNodes)
      }, 500)
    },
    [saveLayoutMutation],
  )

  // ─── 建立連線 ─────────────────────────────────────────────────────────────

  const onConnect = useCallback(
    (connection: Connection) => {
      const sourceVmid =
        connection.source === "gateway"
          ? null
          : parseInt(connection.source!.replace("vm-", ""), 10)
      const targetVmid =
        connection.target === "gateway"
          ? null
          : parseInt(connection.target!.replace("vm-", ""), 10)

      // 兩端都是網關（無意義）
      if (sourceVmid === null && targetVmid === null) {
        toast.error("無法建立網關到網關的連線")
        return
      }

      const sourceName =
        sourceVmid === null
          ? "Internet"
          : (topology?.nodes.find((n) => n.vmid === sourceVmid)?.name ??
            `VM-${sourceVmid}`)
      const targetName =
        targetVmid === null
          ? "Internet"
          : (topology?.nodes.find((n) => n.vmid === targetVmid)?.name ??
            `VM-${targetVmid}`)

      setPendingConnection({ sourceVmid, sourceName, targetVmid, targetName })
    },
    [topology],
  )

  const createConnectionMutation = useMutation({
    mutationFn: ({
      sourceVmid,
      targetVmid,
      ports,
      direction,
    }: {
      sourceVmid: number | null
      targetVmid: number | null
      ports: Array<{ port: number; protocol: string }>
      direction: string
    }) =>
      FirewallService.createFirewallConnection({
        requestBody: {
          source_vmid: sourceVmid!,
          target_vmid: targetVmid,
          ports,
          direction,
        },
      }),
    onSuccess: () => {
      toast.success("連線已建立")
      queryClient.invalidateQueries({ queryKey: ["firewall-topology"] })
    },
    onError: (e: Error) => {
      toast.error(`建立連線失敗: ${e.message}`)
    },
  })

  const handleConnectionConfirm = (
    ports: Array<{ port: number; protocol: string }>,
    direction: "one_way" | "bidirectional",
  ) => {
    if (!pendingConnection) return
    createConnectionMutation.mutate({
      sourceVmid: pendingConnection.sourceVmid,
      targetVmid: pendingConnection.targetVmid,
      ports,
      direction,
    })
    setPendingConnection(null)
  }

  // ─── 節點點擊（顯示規則面板 + 聚焦模式）────────────────────────────────

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      // 聚焦模式：切換（再次點擊同節點取消聚焦）
      setFocusedNodeId((prev) => (prev === node.id ? null : node.id))

      if (node.type === "gateway") {
        setSelectedVmid(null)
        return
      }
      const vmid = parseInt(node.id.replace("vm-", ""), 10)
      const vmName =
        topology?.nodes.find((n) => n.vmid === vmid)?.name ?? `VM-${vmid}`
      setSelectedVmid(vmid)
      setSelectedVmName(vmName)
    },
    [topology],
  )

  const onPaneClick = useCallback(() => {
    setFocusedNodeId(null)
    setSelectedVmid(null)
  }, [])

  // ─── 渲染 ─────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-[#0f0f0f]">
        <div className="text-gray-500 text-sm flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin" />
          載入拓撲資料...
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full bg-[#0f0f0f]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        colorMode="dark"
        className="bg-[#0f0f0f]"
        deleteKeyCode={null} // 停用 Delete 鍵刪除（需透過 UI 確認）
      >
        {/* 點狀網格背景 */}
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#1e1e1e"
        />

        {/* 縮略圖 */}
        <MiniMap
          className="!bg-[#111] !border-[#2e2e2e]"
          nodeColor="#2e2e2e"
          maskColor="rgba(0,0,0,0.6)"
        />

        {/* 控制工具列 */}
        <Controls className="!bg-[#1a1a1a] !border-[#2e2e2e]" />

        {/* 頂部工具列 */}
        <div className="absolute top-4 left-4 z-10 flex items-center gap-2">
          <div className="flex items-center gap-2 bg-[#1a1a1a] border border-[#2e2e2e] rounded-lg px-3 py-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-medium text-gray-200">
              防火牆管理
            </span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => refetch()}
            className="bg-[#1a1a1a] border border-[#2e2e2e] text-gray-400 hover:text-gray-100 h-8"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            重新整理
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={autoArrange}
            className="bg-[#1a1a1a] border border-[#2e2e2e] text-gray-400 hover:text-gray-100 h-8"
          >
            <LayoutGrid className="w-3.5 h-3.5 mr-1.5" />
            自動排列
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowLabels((v) => !v)}
            className={`border h-8 ${
              showLabels
                ? "bg-emerald-900/30 border-emerald-700 text-emerald-400 hover:text-emerald-300"
                : "bg-[#1a1a1a] border-[#2e2e2e] text-gray-400 hover:text-gray-100"
            }`}
          >
            {showLabels ? (
              <Eye className="w-3.5 h-3.5 mr-1.5" />
            ) : (
              <EyeOff className="w-3.5 h-3.5 mr-1.5" />
            )}
            連線標籤
          </Button>
        </div>

        {/* 使用說明 */}
        <div className="absolute bottom-4 left-4 z-10 text-xs text-gray-600 bg-[#111]/80 rounded-md px-3 py-2 border border-[#1e1e1e]">
          拖拉節點移動位置 · 從節點右側拖拉到另一個節點建立連線 · 點擊節點聚焦 ·
          再次點擊或點空白處取消
        </div>
      </ReactFlow>

      {/* 規則側面板 */}
      {selectedVmid !== null && (
        <RulesPanel
          vmid={selectedVmid}
          vmName={selectedVmName}
          onClose={() => {
            setSelectedVmid(null)
            setFocusedNodeId(null)
          }}
        />
      )}

      {/* 建立連線對話框 */}
      <ConnectionDialog
        open={pendingConnection !== null}
        sourceVmid={pendingConnection?.sourceVmid ?? null}
        sourceName={pendingConnection?.sourceName ?? ""}
        targetVmid={pendingConnection?.targetVmid ?? null}
        targetName={pendingConnection?.targetName ?? ""}
        onConfirm={handleConnectionConfirm}
        onClose={() => setPendingConnection(null)}
      />

      {/* 刪除網關警告 */}
      <DeleteGatewayWarning
        open={gatewayWarning !== null}
        vmName={gatewayWarning?.vmName ?? ""}
        onConfirm={() => {
          if (gatewayWarning) {
            deleteConnectionMutation.mutate({
              sourceVmid: gatewayWarning.vmid,
              targetVmid: null,
            })
          }
          setGatewayWarning(null)
        }}
        onClose={() => setGatewayWarning(null)}
      />
    </div>
  )
}

export function FirewallTopology() {
  return (
    <ReactFlowProvider>
      <FirewallTopologyInner />
    </ReactFlowProvider>
  )
}
