import { memo, useCallback, useMemo } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Panel,
  Position,
  type Edge,
  type Node,
  type NodeTypes,
} from 'reactflow'

import 'reactflow/dist/style.css'
import dagre from 'dagre'

import type { FlowEdge, FlowNode, GraphEdge, GraphNode } from './types'

const EntityNode = memo(({ data }: { data: { label: string; content: string } }) => {
  return (
    <div className="px-4 py-2 shadow-md rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 border-2 border-blue-700 min-w-[120px]">
      <Handle type="target" position={Position.Top} />
      <div className="font-semibold text-white text-sm truncate max-w-[200px]" title={data.content}>
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
})

EntityNode.displayName = 'EntityNode'

const ParagraphNode = memo(({ data }: { data: { label: string; content: string } }) => {
  return (
    <div className="px-3 py-2 shadow-md rounded-md bg-gradient-to-br from-green-500 to-green-600 border-2 border-green-700 min-w-[100px]">
      <Handle type="target" position={Position.Top} />
      <div className="font-medium text-white text-xs truncate max-w-[150px]" title={data.content}>
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
})

ParagraphNode.displayName = 'ParagraphNode'

const RelationNode = memo(({ data }: { data: { label: string; content: string } }) => {
  return (
    <div className="px-3 py-2 shadow-md rounded-md bg-gradient-to-br from-amber-500 to-orange-600 border-2 border-orange-700 min-w-[140px]">
      <Handle type="target" position={Position.Top} />
      <div className="font-medium text-white text-xs truncate max-w-[180px]" title={data.content}>
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
})

RelationNode.displayName = 'RelationNode'

const nodeTypes: NodeTypes = {
  entity: EntityNode,
  relation: RelationNode,
  paragraph: ParagraphNode,
}

function calculateLayout(nodes: GraphNode[], edges: GraphEdge[]): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({ rankdir: 'TB', ranksep: 100, nodesep: 80 })

  const flowNodes: FlowNode[] = []
  const flowEdges: FlowEdge[] = []

  nodes.forEach((node) => {
    const size =
      node.type === 'relation'
        ? { width: 180, height: 60 }
        : node.type === 'paragraph'
          ? { width: 190, height: 56 }
          : { width: 150, height: 50 }
    dagreGraph.setNode(node.id, size)
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    flowNodes.push({
      id: node.id,
      type: node.type,
      position: {
        x: nodeWithPosition.x - 75,
        y: nodeWithPosition.y - 25,
      },
      data: {
        label: node.content.slice(0, 20) + (node.content.length > 20 ? '...' : ''),
        content: node.content,
        type: node.type,
      },
    })
  })

  edges.forEach((edge, index) => {
    const isEvidenceEdge = edge.kind && edge.kind !== 'relation'
    const strokeColor =
      edge.kind === 'mentions'
        ? '#0f766e'
        : edge.kind === 'supports'
          ? '#b45309'
          : edge.kind === 'subject'
            ? '#4f46e5'
            : edge.kind === 'object'
              ? '#7c3aed'
              : '#64748b'
    const flowEdge: FlowEdge = {
      id: `edge-${index}`,
      source: edge.source,
      target: edge.target,
      animated: nodes.length <= 200 && (isEvidenceEdge || edge.weight > 5),
      style: {
        strokeWidth: isEvidenceEdge ? Math.min(Math.max(edge.weight, 1.5), 4) : Math.min(edge.weight / 2, 5),
        opacity: isEvidenceEdge ? 0.9 : 0.6,
        stroke: strokeColor,
      },
      labelStyle: {
        fill: '#334155',
        fontSize: 11,
        fontWeight: 600,
      },
      labelBgPadding: [6, 2],
      labelBgBorderRadius: 6,
      labelBgStyle: { fill: 'rgba(255,255,255,0.88)', fillOpacity: 0.95 },
    }
    if (edge.label && (isEvidenceEdge || nodes.length <= 120)) {
      flowEdge.label = edge.label
    } else if (edge.weight > 10 && nodes.length < 100) {
      flowEdge.label = `${edge.weight.toFixed(0)}`
    }
    flowEdges.push(flowEdge)
  })

  return { nodes: flowNodes, edges: flowEdges }
}

interface GraphVisualizationProps {
  graphData: { nodes: GraphNode[]; edges: GraphEdge[] }
  onNodeClick: (event: React.MouseEvent, node: Node) => void
  onEdgeClick: (event: React.MouseEvent, edge: Edge) => void
  loading?: boolean
}

export function GraphVisualization({ graphData, onNodeClick, onEdgeClick, loading = false }: GraphVisualizationProps) {
  const { nodes: flowNodes, edges: flowEdges } = useMemo(
    () => calculateLayout(graphData.nodes, graphData.edges),
    [graphData.edges, graphData.nodes],
  )
  const nodeCount = flowNodes.length
  const graphMode = useMemo(
    () => (graphData.nodes.some((node) => node.type !== 'entity') ? 'evidence' : 'entity'),
    [graphData.nodes],
  )

  const miniMapNodeColor = useCallback((node: Node) => {
    if (node.type === 'entity') return '#6366f1'
    if (node.type === 'relation') return '#f59e0b'
    if (node.type === 'paragraph') return '#10b981'
    return '#6b7280'
  }, [])

  if (loading) {
    return null
  }

  return (
    <div
      style={{ touchAction: 'none' }}
      role="img"
      aria-label={`知识图谱可视化，共 ${nodeCount} 个节点，${flowEdges.length} 条关系`}
      className="w-full h-full"
    >
      <span className="sr-only">
        {`知识图谱包含 ${nodeCount} 个节点和 ${flowEdges.length} 条关系。`}
      </span>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.05}
        maxZoom={1.5}
        defaultViewport={{ x: 0, y: 0, zoom: 0.5 }}
        elevateNodesOnSelect={nodeCount <= 500}
        nodesDraggable={nodeCount <= 1000}
        attributionPosition="bottom-left"
        panOnScroll
        panOnScrollMode={undefined}
        panOnDrag
        zoomOnPinch
      >
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
        <Controls />
        {nodeCount <= 500 && (
          <MiniMap
            nodeColor={miniMapNodeColor}
            nodeBorderRadius={8}
            pannable
            zoomable
          />
        )}

        <Panel position="top-right" className="bg-background/95 backdrop-blur-sm rounded-lg border p-3 shadow-lg">
          <div className="text-sm font-semibold mb-2">
            {graphMode === 'entity' ? '实体关系图图例' : '证据视图图例'}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-gradient-to-br from-blue-500 to-blue-600 border-2 border-blue-700" aria-hidden="true" />
              <span>实体节点</span>
            </div>
            {graphMode === 'evidence' && (
              <>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded bg-gradient-to-br from-amber-500 to-orange-600 border-2 border-orange-700" aria-hidden="true" />
                  <span>关系节点</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded bg-gradient-to-br from-green-500 to-green-600 border-2 border-green-700" aria-hidden="true" />
                  <span>段落节点</span>
                </div>
                <div className="text-muted-foreground">
                  紫色线表示关系到宾语，蓝色线表示关系到主语，绿色/橙色线表示段落证据。
                </div>
              </>
            )}
            {graphMode === 'entity' && (
              <div className="text-muted-foreground">
                线条表示实体间聚合关系，边标签优先显示主谓词，更多语义可点击查看详情。
              </div>
            )}
            {nodeCount > 200 && (
              <div className="mt-2 pt-2 border-t text-yellow-600 dark:text-yellow-500">
                <div className="font-semibold">性能模式</div>
                <div>已禁用动画</div>
                {nodeCount > 500 && <div>已禁用缩略图</div>}
              </div>
            )}
          </div>
        </Panel>
      </ReactFlow>
    </div>
  )
}
