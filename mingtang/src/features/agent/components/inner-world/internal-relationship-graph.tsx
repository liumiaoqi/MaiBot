import { Component, type ReactNode } from 'react'
import { useMemo, useState, useCallback } from 'react'

import {
  Background,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type EdgeMouseHandler,
  type Node,
} from '@xyflow/react'

import '@xyflow/react/dist/style.css'

import type { InternalRelationship, AgentConfigInfo } from '@/lib/agent-api'
import { REL_TYPE_COLORS } from './relationship-network'

interface InternalRelNodeData {
  agentId: string
  displayName: string
  color: string
  isSelf: boolean
  [key: string]: unknown
}

interface InternalRelEdgeData {
  relationshipType: string
  attitude: string
  interactionStyle: string
  mentionTendency: number
  color: string
  [key: string]: unknown
}

const NODE_SIZE = 36
const RADIAL_RADIUS = 100

// dagre 缺失（mingtang 无此依赖）→ 星型布局替代：self 居中，其余节点环绕
function layoutWithRadial<N extends Node & { data: InternalRelNodeData }, E extends Edge>(
  nodes: N[],
  edges: E[],
): { nodes: N[]; edges: E[] } {
  const selfNode = nodes.find((n) => n.data.isSelf)
  const others = nodes.filter((n) => n !== selfNode)

  const layouted: N[] = []
  if (selfNode) {
    layouted.push({ ...selfNode, position: { x: 0, y: 0 } })
  }
  others.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2
    layouted.push({
      ...node,
      position: {
        x: RADIAL_RADIUS * Math.cos(angle),
        y: RADIAL_RADIUS * Math.sin(angle),
      },
    })
  })

  return { nodes: layouted, edges }
}

function InternalRelNode({ data }: { data: InternalRelNodeData }) {
  return (
    <div className="flex flex-col items-center" style={{ width: NODE_SIZE + 20 }}>
      <div
        className="rounded-full flex items-center justify-center text-white text-xs font-bold"
        style={{
          width: NODE_SIZE,
          height: NODE_SIZE,
          backgroundColor: data.color,
          opacity: data.isSelf ? 1 : 0.85,
          boxShadow: data.isSelf ? `0 0 0 2px var(--color-background), 0 0 0 4px ${data.color}` : undefined,
        }}
      >
        {data.displayName.charAt(0)}
      </div>
      <span className="text-[10px] text-muted-foreground mt-1 truncate max-w-[56px] text-center">
        {data.displayName}
      </span>
    </div>
  )
}

const nodeTypes = { internalRel: InternalRelNode }

interface InternalRelationshipGraphProps {
  agentId: string
  internalRelationships: InternalRelationship[]
  agents: AgentConfigInfo[]
  hotspotPairs?: Set<string>
}

function InternalRelationshipGraphInner({
  agentId,
  internalRelationships,
  agents,
  hotspotPairs,
}: InternalRelationshipGraphProps) {
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null)

  const agentMap = useMemo(() => {
    const map = new Map<string, AgentConfigInfo>()
    for (const a of agents) map.set(a.agent_id, a)
    return map
  }, [agents])

  const initialNodes = useMemo(() => {
    const self = agentMap.get(agentId)
    const nodeData: {
      id: string
      type: 'internalRel'
      position: { x: number; y: number }
      data: InternalRelNodeData
    }[] = [
      {
        id: agentId,
        type: 'internalRel',
        position: { x: 0, y: 0 },
        data: {
          agentId,
          displayName: self?.display_name ?? agentId,
          // `#6b7280` 为 agent 未配置颜色时的兜底色（数据可视化色板豁免）
          color: self?.color ?? '#6b7280',
          isSelf: true,
        } satisfies InternalRelNodeData,
      },
    ]

    for (const rel of internalRelationships) {
      const target = agentMap.get(rel.target_agent_id)
      nodeData.push({
        id: rel.target_agent_id,
        type: 'internalRel',
        position: { x: 0, y: 0 },
        data: {
          agentId: rel.target_agent_id,
          displayName: target?.display_name ?? rel.target_agent_id,
          // `#6b7280` 为 agent 未配置颜色时的兜底色（数据可视化色板豁免）
          color: target?.color ?? '#6b7280',
          isSelf: false,
        } satisfies InternalRelNodeData,
      })
    }

    return nodeData
  }, [agentId, internalRelationships, agentMap])

  const initialEdges = useMemo(
    () =>
      internalRelationships.map((rel) => {
        const pairKey = `${agentId}:${rel.target_agent_id}`
        const reversePairKey = `${rel.target_agent_id}:${agentId}`
        const isHotspot = hotspotPairs?.has(pairKey) || hotspotPairs?.has(reversePairKey) || false
        // `#94a3b8` 为 REL_TYPE_COLORS 缺失兜底色；`#f97316` 为 hotspot 高亮色（数据可视化色板豁免）
        const baseColor = REL_TYPE_COLORS[rel.relationship_type] || '#94a3b8'
        return {
          id: `${agentId}-${rel.target_agent_id}`,
          source: agentId,
          target: rel.target_agent_id,
          animated: isHotspot || rel.mention_tendency >= 0.7,
          style: {
            // `#f97316` 为 hotspot 高亮色（数据可视化色板豁免）
            stroke: isHotspot ? '#f97316' : baseColor,
            strokeWidth: isHotspot
              ? Math.round(rel.mention_tendency * 3 + 3)
              : Math.round(rel.mention_tendency * 3 + 1),
          },
          data: {
            relationshipType: rel.relationship_type,
            attitude: rel.attitude,
            interactionStyle: rel.interaction_style,
            mentionTendency: rel.mention_tendency,
            // `#f97316` 为 hotspot 高亮色（数据可视化色板豁免）
            color: isHotspot ? '#f97316' : baseColor,
            isHotspot,
          } satisfies InternalRelEdgeData & { isHotspot: boolean },
        }
      }),
    [agentId, internalRelationships, hotspotPairs],
  )

  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => layoutWithRadial(initialNodes, initialEdges),
    [initialNodes, initialEdges],
  )

  const [nodes, , onNodesChange] = useNodesState(layoutedNodes)
  const [edges, , onEdgesChange] = useEdgesState(layoutedEdges)

  const handleEdgeMouseEnter: EdgeMouseHandler = useCallback((_event, edge) => {
    setHoveredEdgeId(edge.id)
  }, [])

  const handleEdgeMouseLeave: EdgeMouseHandler = useCallback(() => {
    setHoveredEdgeId(null)
    setTooltipPosition(null)
  }, [])

  const handleEdgeMouseMove = useCallback((event: React.MouseEvent) => {
    setTooltipPosition({ x: event.clientX, y: event.clientY })
  }, [])

  const hoveredEdgeData = hoveredEdgeId
    ? edges.find((e) => e.id === hoveredEdgeId)?.data
    : undefined

  return (
    <div className="h-[200px] w-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onEdgeMouseEnter={handleEdgeMouseEnter}
        onEdgeMouseLeave={handleEdgeMouseLeave}
        onEdgeMouseMove={handleEdgeMouseMove}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.5}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="var(--color-border)" gap={20} size={1} />
      </ReactFlow>

      {hoveredEdgeData && tooltipPosition && (
        <div
          className="absolute z-50 pointer-events-none"
          style={{ left: tooltipPosition.x + 12, top: tooltipPosition.y + 12 }}
        >
          <div className="bg-popover text-popover-foreground rounded-lg border shadow-md p-2.5 text-xs space-y-1">
            <div className="font-medium flex items-center gap-1" style={{ color: hoveredEdgeData.color }}>
              {hoveredEdgeData.relationshipType}
              {hoveredEdgeData.isHotspot && (
                <span className="text-orange-400">🔥</span>
              )}
            </div>
            <div className="text-muted-foreground">{hoveredEdgeData.attitude}</div>
            {hoveredEdgeData.interactionStyle && (
              <div className="text-muted-foreground">{hoveredEdgeData.interactionStyle}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

class InternalRelationshipGraphErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}

export function InternalRelationshipGraph(props: InternalRelationshipGraphProps) {
  const fallback = (
    <div className="space-y-2">
      {props.internalRelationships.map((rel) => (
        <div key={rel.target_agent_id} className="flex items-center gap-2 text-sm">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            // `#94a3b8` 为 REL_TYPE_COLORS 缺失兜底色（数据可视化色板豁免）
            style={{ backgroundColor: REL_TYPE_COLORS[rel.relationship_type] || '#94a3b8' }}
          />
          <span className="font-medium">{rel.target_agent_id}</span>
          <span className="text-muted-foreground">{rel.relationship_type}</span>
          <span className="text-muted-foreground">—</span>
          <span>{rel.attitude}</span>
        </div>
      ))}
    </div>
  )

  return (
    <InternalRelationshipGraphErrorBoundary fallback={fallback}>
      <InternalRelationshipGraphInner {...props} />
    </InternalRelationshipGraphErrorBoundary>
  )
}