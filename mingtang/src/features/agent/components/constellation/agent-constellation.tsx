import { useCallback, useMemo, useState } from 'react'

import {
  Background,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type EdgeMouseHandler,
  type NodeMouseHandler,
} from '@xyflow/react'
import { useTranslation } from 'react-i18next'

import '@xyflow/react/dist/style.css'

import type { AgentConfigInfo, BatchEmotionItem } from '@/lib/agent-api'
import { layoutRadial } from '../../utils/graph-layout'
import type { ConstellationData, ConstellationEdge as ConstellationEdgeData, ConstellationNode as ConstellationNodeData } from '../../utils/constellation'
import { ConstellationEdgeComponent } from './constellation-edge'
import { ConstellationNodeComponent } from './constellation-node'
import { NodeDetailPopover } from './node-detail-popover'
import { RelationshipTooltip } from './relationship-tooltip'

const nodeTypes = { constellation: ConstellationNodeComponent }
const edgeTypes = { constellation: ConstellationEdgeComponent }

const RADIAL_RADIUS = 180

interface AgentConstellationProps {
  data: ConstellationData
  onNodeClick: (agentId: string) => void
  onNodeDoubleClick: (agentId: string) => void
  emotions: Record<string, BatchEmotionItem>
  sessionCounts: Record<string, number>
  agents: AgentConfigInfo[]
}

export function AgentConstellation({
  data,
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

  const initialNodes = useMemo(() =>
    data.nodes.map((n) => ({
      id: n.id,
      type: 'constellation',
      position: { x: 0, y: 0 },
      data: n,
    })),
    [data.nodes]
  )

  const initialEdges = useMemo(() =>
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
    () => layoutRadial(initialNodes, initialEdges, { radius: RADIAL_RADIUS }),
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

  const handleNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setHighlightedNodeId(node.id)
    setHoveredEdgeId(null)
    onNodeClick(node.id)
  }, [onNodeClick])

  const handleNodeDoubleClick: NodeMouseHandler = useCallback((_event, node) => {
    onNodeDoubleClick(node.id)
  }, [onNodeDoubleClick])

  const handlePaneClick = useCallback(() => {
    setHighlightedNodeId(null)
    setPopoverPosition(null)
  }, [])

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
        <Background color="var(--color-border)" gap={20} size={1} />
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