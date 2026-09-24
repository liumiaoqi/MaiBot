import { useCallback, useMemo, useState } from 'react'

import ReactFlow, { useNodesState, useEdgesState, Background, type Node, type Edge, type NodeMouseHandler, type EdgeMouseHandler } from 'reactflow'
import dagre from 'dagre'
import { useTranslation } from 'react-i18next'

import 'reactflow/dist/style.css'

import type { ConstellationData, ConstellationNode as ConstellationNodeData, ConstellationEdge as ConstellationEdgeData } from '../../utils/constellation'
import { ConstellationNodeComponent } from './ConstellationNode'
import { ConstellationEdgeComponent } from './ConstellationEdge'
import { NodeDetailPopover } from './NodeDetailPopover'
import { RelationshipTooltip } from './RelationshipTooltip'
import type { BatchEmotionItem, AgentConfigInfo } from '@/lib/agent-api'

const nodeTypes = { constellation: ConstellationNodeComponent }
const edgeTypes = { constellation: ConstellationEdgeComponent as any }

function layoutWithDagre(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 80, ranksep: 100 })

  for (const node of nodes) {
    g.setNode(node.id, { width: 80, height: 80 })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: { x: pos.x - 40, y: pos.y - 40 },
    }
  })

  return { nodes: layoutedNodes, edges }
}

interface AgentConstellationProps {
  data: ConstellationData
  selectedAgentId: string | null
  onNodeClick: (agentId: string) => void
  onNodeDoubleClick: (agentId: string) => void
  emotions: Record<string, BatchEmotionItem>
  sessionCounts: Record<string, number>
  agents: AgentConfigInfo[]
}

export function AgentConstellation({
  data,
  selectedAgentId: _selectedAgentId,
  onNodeClick,
  onNodeDoubleClick,
  emotions,
  sessionCounts,
  agents,
}: AgentConstellationProps) {
  const { t } = useTranslation()

  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null)
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)
  const [popoverPosition, setPopoverPosition] = useState<{ x: number; y: number } | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null)

  const initialNodes: Node[] = useMemo(() =>
    data.nodes.map((n) => ({
      id: n.id,
      type: 'constellation',
      position: { x: 0, y: 0 },
      data: n,
    })),
    [data.nodes]
  )

  const initialEdges: Edge[] = useMemo(() =>
    data.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'constellation',
      data: e,
    })),
    [data.edges]
  )

  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => layoutWithDagre(initialNodes, initialEdges),
    [initialNodes, initialEdges]
  )

  const activeHighlight = highlightedNodeId

  const highlightedNodes = useMemo(() => {
    if (!activeHighlight) return layoutedNodes
    const connectedEdges = layoutedEdges.filter(
      (e) => e.source === activeHighlight || e.target === activeHighlight
    )
    const connectedNodeIds = new Set([
      activeHighlight,
      ...connectedEdges.map((e) => e.source),
      ...connectedEdges.map((e) => e.target),
    ])
    return layoutedNodes.map((node) => ({
      ...node,
      style: {
        opacity: connectedNodeIds.has(node.id) ? 1 : 0.4,
      },
    }))
  }, [layoutedNodes, layoutedEdges, activeHighlight])

  const highlightedEdges = useMemo(() => {
    if (!activeHighlight) return layoutedEdges
    const relatedEdges = layoutedEdges.filter(
      (e) => e.source === activeHighlight || e.target === activeHighlight
    )
    const relatedIds = new Set(relatedEdges.map((e) => e.id))
    return layoutedEdges.map((edge) => ({
      ...edge,
      style: {
        opacity: relatedIds.has(edge.id) ? 1 : 0.2,
      },
    }))
  }, [layoutedEdges, activeHighlight])

  const [nodes, , onNodesChange] = useNodesState(highlightedNodes)
  const [edges, , onEdgesChange] = useEdgesState(highlightedEdges)

  const handleNodeClick: NodeMouseHandler = useCallback((_: any, node: Node) => {
    setHighlightedNodeId(node.id)
    setHoveredEdgeId(null)
    onNodeClick(node.id)
  }, [onNodeClick])

  const handleNodeDoubleClick = useCallback((_: any, node: Node) => {
    onNodeDoubleClick(node.id)
  }, [onNodeDoubleClick])

  const handlePaneClick = useCallback(() => {
    setHighlightedNodeId(null)
    setPopoverPosition(null)
  }, [])

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


  const selectedNodeData: ConstellationNodeData | undefined = highlightedNodeId
    ? data.nodes.find((n) => n.id === highlightedNodeId)
    : undefined

  const hoveredEdgeData: ConstellationEdgeData | undefined = hoveredEdgeId
    ? data.edges.find((e) => e.id === hoveredEdgeId)
    : undefined

  if (data.nodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        {t('agent.constellation.noRelationships')}
      </div>
    )
  }

  return (
    <div className="flex-1 h-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onPaneClick={handlePaneClick}
        onEdgeMouseEnter={handleEdgeMouseEnter}
        onEdgeMouseLeave={handleEdgeMouseLeave}
        onEdgeMouseMove={handleEdgeMouseMove}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="hsl(var(--border))" gap={20} size={1} />
      </ReactFlow>

      {selectedNodeData && popoverPosition && (
        <div
          className="absolute z-50 pointer-events-none"
          style={{ left: popoverPosition.x, top: popoverPosition.y }}
        >
          <NodeDetailPopover
            data={selectedNodeData}
            emotion={emotions[selectedNodeData.id]}
            sessionCount={sessionCounts[selectedNodeData.id] ?? 0}
            talkValueModifier={agents.find((a) => a.agent_id === selectedNodeData.id)?.talk_value_modifier ?? 1.0}
          />
        </div>
      )}

      {hoveredEdgeData && tooltipPosition && (
        <div
          className="absolute z-50 pointer-events-none"
          style={{ left: tooltipPosition.x + 12, top: tooltipPosition.y + 12 }}
        >
          <RelationshipTooltip data={hoveredEdgeData} />
        </div>
      )}
    </div>
  )
}
