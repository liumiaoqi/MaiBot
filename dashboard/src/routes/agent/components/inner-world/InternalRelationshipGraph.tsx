import { Component, type ReactNode } from 'react'
import { useMemo, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import ReactFlow, { useNodesState, useEdgesState, Background, type Node, type Edge, type EdgeMouseHandler } from 'reactflow'
import dagre from 'dagre'

import 'reactflow/dist/style.css'

import type { InternalRelationship, AgentConfigInfo } from '@/lib/agent-api'
import { REL_TYPE_COLORS } from './RelationshipNetwork'

interface InternalRelNodeData {
  agentId: string
  displayName: string
  color: string
  isSelf: boolean
}

interface InternalRelEdgeData {
  relationshipType: string
  attitude: string
  interactionStyle: string
  mentionTendency: number
  color: string
}

const NODE_SIZE = 36

function layoutWithDagre(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 80 })

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_SIZE + 20, height: NODE_SIZE + 20 })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: { x: pos.x - (NODE_SIZE + 20) / 2, y: pos.y - (NODE_SIZE + 20) / 2 },
    }
  })

  return { nodes: layoutedNodes, edges }
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
          boxShadow: data.isSelf ? `0 0 0 2px var(--background), 0 0 0 4px ${data.color}` : undefined,
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

function InternalRelationshipGraphInner({
  agentId,
  internalRelationships,
  agents,
  hotspotPairs,
}: InternalRelationshipGraphProps) {
  const { t } = useTranslation()
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null)

  const agentMap = useMemo(() => {
    const map = new Map<string, AgentConfigInfo>()
    for (const a of agents) map.set(a.agent_id, a)
    return map
  }, [agents])

  const initialNodes: Node[] = useMemo(() => {
    const self = agentMap.get(agentId)
    const nodeData: Node[] = [
      {
        id: agentId,
        type: 'internalRel',
        position: { x: 0, y: 0 },
        data: {
          agentId,
          displayName: self?.display_name ?? agentId,
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
          color: target?.color ?? '#6b7280',
          isSelf: false,
        } satisfies InternalRelNodeData,
      })
    }

    return nodeData
  }, [agentId, internalRelationships, agentMap])

  const initialEdges: Edge[] = useMemo(() =>
    internalRelationships.map((rel) => {
      const pairKey = `${agentId}:${rel.target_agent_id}`
      const reversePairKey = `${rel.target_agent_id}:${agentId}`
      const isHotspot = hotspotPairs?.has(pairKey) || hotspotPairs?.has(reversePairKey) || false
      const baseColor = REL_TYPE_COLORS[rel.relationship_type] || '#94a3b8'
      return {
        id: `${agentId}-${rel.target_agent_id}`,
        source: agentId,
        target: rel.target_agent_id,
        animated: isHotspot || rel.mention_tendency >= 0.7,
        style: {
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
          color: isHotspot ? '#f97316' : baseColor,
          isHotspot,
        } satisfies InternalRelEdgeData & { isHotspot: boolean },
      }
    }),
    [agentId, internalRelationships, hotspotPairs],
  )

  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => layoutWithDagre(initialNodes, initialEdges),
    [initialNodes, initialEdges],
  )

  const [nodes, , onNodesChange] = useNodesState(layoutedNodes)
  const [edges, , onEdgesChange] = useEdgesState(layoutedEdges)

  const handleEdgeMouseEnter: EdgeMouseHandler = useCallback((_: any, edge: Edge) => {
    setHoveredEdgeId(edge.id)
  }, [])

  const handleEdgeMouseLeave: EdgeMouseHandler = useCallback(() => {
    setHoveredEdgeId(null)
    setTooltipPosition(null)
  }, [])

  const handleEdgeMouseMove = useCallback((event: React.MouseEvent) => {
    setTooltipPosition({ x: event.clientX, y: event.clientY })
  }, [])

  const hoveredEdgeData: (InternalRelEdgeData & { isHotspot?: boolean }) | undefined = hoveredEdgeId
    ? edges.find((e) => e.id === hoveredEdgeId)?.data as (InternalRelEdgeData & { isHotspot?: boolean }) | undefined
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
        <Background color="hsl(var(--border))" gap={20} size={1} />
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

interface InternalRelationshipGraphProps {
  agentId: string
  internalRelationships: InternalRelationship[]
  agents: AgentConfigInfo[]
  hotspotPairs?: Set<string>
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
  const { t } = useTranslation()

  const fallback = (
    <div className="space-y-2">
      {props.internalRelationships.map((rel) => (
        <div key={rel.target_agent_id} className="flex items-center gap-2 text-sm">
          <span
            className="w-2 h-2 rounded-full shrink-0"
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