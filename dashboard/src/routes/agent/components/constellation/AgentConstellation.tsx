import { useCallback, useMemo, useState } from 'react'

import ReactFlow, { useNodesState, useEdgesState, Background, type Node, type Edge } from 'reactflow'
import dagre from 'dagre'
import { useTranslation } from 'react-i18next'

import 'reactflow/dist/style.css'

import type { ConstellationData } from '../../utils/constellation'
import { ConstellationNodeComponent } from './ConstellationNode'
import { ConstellationEdgeComponent } from './ConstellationEdge'

const nodeTypes = { constellation: ConstellationNodeComponent }
const edgeTypes = { constellation: ConstellationEdgeComponent }

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
}

export function AgentConstellation({ data, selectedAgentId, onNodeClick, onNodeDoubleClick }: AgentConstellationProps) {
  const { t } = useTranslation()

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

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges)

  const handleNodeClick = useCallback((_: any, node: Node) => {
    onNodeClick(node.id)
  }, [onNodeClick])

  const handleNodeDoubleClick = useCallback((_: any, node: Node) => {
    onNodeDoubleClick(node.id)
  }, [onNodeDoubleClick])

  if (data.nodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        {t('agent.constellation.noRelationships')}
      </div>
    )
  }

  return (
    <div className="flex-1 h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="hsl(var(--border))" gap={20} size={1} />
      </ReactFlow>
    </div>
  )
}