/**
 * useGraphExplorer —— 记忆图谱「图谱加载 + 搜索 + 视图切换 + 选中态」领域 hook
 * （R3 遗留 D6：P2-B 从 knowledge-graph.tsx 迁出，纯函数搬家、行为不变）。
 *
 * 收编与图谱探索相关的状态与交互：
 * - 图谱加载（nodeLimit 上限、刷新、深链静默加载）；
 * - 搜索（后端全库检索 + 失败回退本地筛选）；
 * - 实体/证据视图切换与节点/边/关系/段落的选中详情；
 * - 删除预览-执行相关的状态与回调不在本 hook（见 use-graph-delete.ts）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { Edge, Node } from '@xyflow/react'
import { toast } from 'sonner'

import {
  getMemoryGraph,
  getMemoryGraphEdgeDetail,
  getMemoryGraphNodeDetail,
  getMemoryGraphParagraphDetail,
  getMemoryGraphSearch,
  type MemoryEvidenceParagraphNodeMetadata,
  type MemoryEvidenceRelationNodeMetadata,
  type MemoryGraphEdgeDetailPayload,
  type MemoryGraphNodeDetailPayload,
  type MemoryGraphParagraphDetailPayload,
  type MemoryGraphPayload,
  type MemoryGraphRelationDetailPayload,
  type MemoryGraphSearchItem,
} from '@/lib/memory-api'

import {
  buildParagraphFromMetadata,
  buildRelationFromMetadata,
  filterGraphData,
  mergeUniqueParagraphs,
  mergeUniqueRelations,
  toEntityGraphData,
  toEvidenceGraphData,
} from '../graph-transform'
import type { GraphData, GraphNode, SelectedEdgeData } from '../types/graph-types'

export type GraphViewMode = 'entity' | 'evidence'

/** 深链/删除后恢复目标：回到哪一个视图位置 */
export type GraphRestoreTarget =
  | { type: 'entity'; nodeId: string; viewMode: GraphViewMode }
  | { type: 'edge'; source: string; target: string; viewMode: GraphViewMode }
  | { type: 'paragraph'; paragraphHash: string; viewMode: GraphViewMode }
  | { type: 'view'; viewMode: GraphViewMode }

export interface UseGraphExplorerOptions {
  /** 深链段落 hash：挂载后静默定位该段落（证据视图） */
  initialParagraphHash?: string
}

export function useGraphExplorer({ initialParagraphHash = '' }: UseGraphExplorerOptions) {
  const [loading, setLoading] = useState(false)
  const [nodeLimit, setNodeLimit] = useState('120')
  const [searchInput, setSearchInput] = useState('')
  const [appliedSearchQuery, setAppliedSearchQuery] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchResults, setSearchResults] = useState<MemoryGraphSearchItem[]>([])
  const [searchFallbackMode, setSearchFallbackMode] = useState(false)
  const [viewMode, setViewMode] = useState<GraphViewMode>('entity')
  const [fullGraph, setFullGraph] = useState<GraphData>({ nodes: [], edges: [] })
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] })
  const [evidenceGraph, setEvidenceGraph] = useState<GraphData>({ nodes: [], edges: [] })
  const [graphMeta, setGraphMeta] = useState<MemoryGraphPayload | null>(null)
  const [selectedNodeData, setSelectedNodeData] = useState<GraphNode | null>(null)
  const [selectedEdgeData, setSelectedEdgeData] = useState<SelectedEdgeData | null>(null)
  const [nodeDetail, setNodeDetail] = useState<MemoryGraphNodeDetailPayload | null>(null)
  const [edgeDetail, setEdgeDetail] = useState<MemoryGraphEdgeDetailPayload | null>(null)
  const [selectedRelationDetail, setSelectedRelationDetail] = useState<MemoryGraphRelationDetailPayload | null>(null)
  const [selectedRelationMetadata, setSelectedRelationMetadata] = useState<MemoryEvidenceRelationNodeMetadata | null>(null)
  const [selectedParagraphDetail, setSelectedParagraphDetail] = useState<MemoryGraphParagraphDetailPayload | null>(null)
  const [selectedParagraphMetadata, setSelectedParagraphMetadata] = useState<MemoryEvidenceParagraphNodeMetadata | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  // 已处理 hash 标记——防重复深链处理——ref 即可（无需渲染——审核修复）
  const appliedInitialParagraphHashRef = useRef('')

  const allRelationDetails = useMemo(
    () => mergeUniqueRelations(nodeDetail, edgeDetail),
    [edgeDetail, nodeDetail],
  )
  const allParagraphDetails = useMemo(
    () => mergeUniqueParagraphs(nodeDetail, edgeDetail),
    [edgeDetail, nodeDetail],
  )

  const resetDetailSelections = useCallback(() => {
    setSelectedNodeData(null)
    setSelectedEdgeData(null)
    setNodeDetail(null)
    setEdgeDetail(null)
    setSelectedRelationDetail(null)
    setSelectedRelationMetadata(null)
    setSelectedParagraphDetail(null)
    setSelectedParagraphMetadata(null)
  }, [])

  const loadGraph = useCallback(async (options?: { silent?: boolean; keepSelection?: boolean }) => {
    try {
      // silent = 静默加载（深链场景）——不同步 setLoading（避免 effect 内同步 setState——lint 规则）
      if (!options?.silent) {
        setLoading(true)
      }
      const payload = await getMemoryGraph(Number(nodeLimit))
      const nextGraph = toEntityGraphData(payload)
      const visibleGraph = searchFallbackMode && appliedSearchQuery
        ? filterGraphData(nextGraph, appliedSearchQuery)
        : nextGraph
      setGraphMeta(payload)
      setFullGraph(nextGraph)
      setGraphData(visibleGraph)
      if (!options?.keepSelection) {
        setEvidenceGraph({ nodes: [], edges: [] })
        resetDetailSelections()
      }
      if (!options?.silent) {
        toast.success('图谱已更新', {
          description: `当前加载 ${nextGraph.nodes.length} 个节点、${nextGraph.edges.length} 条关系`,
        })
      }
    } catch (error) {
      toast.error('加载失败', {
        description: error instanceof Error ? error.message : '未知错误',
      })
    } finally {
      setLoading(false)
    }
  }, [appliedSearchQuery, nodeLimit, resetDetailSelections, searchFallbackMode])

  useEffect(() => {
    // 深链 hash → 静默加载——setTimeout 调度（渲染提交后异步执行——effect 内不直接调用
    // 含同步 setState 的函数——lint 规则；带 cleanup 的合法 effect 异步模式）
    const timer = setTimeout(() => {
      void loadGraph({ silent: true, keepSelection: Boolean(initialParagraphHash.trim()) })
    }, 0)
    return () => clearTimeout(timer)
  }, [initialParagraphHash, loadGraph])

  const handleSearch = useCallback(async () => {
    const nextQuery = searchInput.trim()
    if (!nextQuery) {
      setAppliedSearchQuery('')
      setSearchFallbackMode(false)
      setSearchResults([])
      setGraphData(fullGraph)
      toast.success('已重置筛选', {
        description: `当前显示 ${fullGraph.nodes.length} 个节点、${fullGraph.edges.length} 条关系`,
      })
      return
    }
    setSearchLoading(true)
    setAppliedSearchQuery(nextQuery)
    try {
      const payload = await getMemoryGraphSearch(nextQuery, 50)
      if (payload.error) {
        throw new Error(payload.error || '图谱检索失败')
      }
      const items = Array.isArray(payload.items) ? payload.items : []
      setSearchResults(items)
      setSearchFallbackMode(false)
      setGraphData(fullGraph)
      toast.success('全库检索完成', {
        description: `命中 ${payload.count ?? items.length} 条结果`,
      })
    } catch {
      const filtered = filterGraphData(fullGraph, nextQuery)
      setSearchResults([])
      setSearchFallbackMode(true)
      setGraphData(filtered)
      toast.error('后端检索失败，已回退本地筛选', {
        description: `仅当前已加载范围（${filtered.nodes.length} 个节点、${filtered.edges.length} 条关系）`,
      })
    } finally {
      setSearchLoading(false)
    }
  }, [fullGraph, searchInput])

  const stats = useMemo(
    () => ({
      totalNodes: graphMeta?.total_nodes ?? fullGraph.nodes.length,
      totalEdges: graphMeta?.total_edges ?? fullGraph.edges.length,
      visibleNodes: graphData.nodes.length,
      visibleEdges: graphData.edges.length,
      evidenceNodes: evidenceGraph.nodes.length,
      evidenceEdges: evidenceGraph.edges.length,
    }),
    [
      evidenceGraph.edges.length,
      evidenceGraph.nodes.length,
      fullGraph.edges.length,
      fullGraph.nodes.length,
      graphData.edges.length,
      graphData.nodes.length,
      graphMeta,
    ],
  )

  const openNodeDetail = useCallback(async (
    nodeId: string,
    options?: { locateInEvidence?: boolean },
  ) => {
    const nodeToken = String(nodeId || '').trim()
    if (!nodeToken) {
      return
    }
    const selected = graphData.nodes.find((item) => item.id === nodeToken)
    if (options?.locateInEvidence) {
      setSelectedNodeData(null)
    } else {
      setSelectedNodeData(
        selected ?? {
          id: nodeToken,
          type: 'entity',
          content: nodeToken,
          metadata: {},
        },
      )
    }
    setSelectedEdgeData(null)
    setNodeDetail(null)
    setEdgeDetail(null)
    setSelectedRelationDetail(null)
    setSelectedRelationMetadata(null)
    setSelectedParagraphDetail(null)
    setSelectedParagraphMetadata(null)
    try {
      setDetailLoading(true)
      const detail = await getMemoryGraphNodeDetail(nodeToken)
      setNodeDetail(detail)
      setEvidenceGraph(toEvidenceGraphData(detail.evidence_graph))
      if (options?.locateInEvidence) {
        setViewMode('evidence')
      }
    } catch (error) {
      setSelectedNodeData(null)
      setNodeDetail(null)
      setEvidenceGraph({ nodes: [], edges: [] })
      setViewMode('entity')
      toast.error('加载节点详情失败', {
        description: error instanceof Error ? error.message : '未知错误',
      })
    } finally {
      setDetailLoading(false)
    }
  }, [graphData.nodes])

  const openEdgeDetail = useCallback(async (
    source: string,
    target: string,
    options?: { locateInEvidence?: boolean },
  ) => {
    const sourceToken = String(source || '').trim()
    const targetToken = String(target || '').trim()
    if (!sourceToken || !targetToken) {
      return
    }
    setSelectedNodeData(null)
    setNodeDetail(null)
    setEdgeDetail(null)
    setSelectedRelationDetail(null)
    setSelectedRelationMetadata(null)
    setSelectedParagraphDetail(null)
    setSelectedParagraphMetadata(null)
    if (options?.locateInEvidence) {
      setSelectedEdgeData(null)
    } else {
      const sourceNode = graphData.nodes.find((nodeItem) => nodeItem.id === sourceToken) ?? {
        id: sourceToken,
        type: 'entity' as const,
        content: sourceToken,
        metadata: {},
      }
      const targetNode = graphData.nodes.find((nodeItem) => nodeItem.id === targetToken) ?? {
        id: targetToken,
        type: 'entity' as const,
        content: targetToken,
        metadata: {},
      }
      const edgeData = graphData.edges.find((item) => item.source === sourceToken && item.target === targetToken) ?? {
        source: sourceToken,
        target: targetToken,
        weight: 1,
        kind: 'relation' as const,
        label: '',
        relationHashes: [],
        predicates: [],
        relationCount: 0,
        evidenceCount: 0,
      }
      setSelectedEdgeData({
        source: sourceNode,
        target: targetNode,
        edge: edgeData,
      })
    }
    try {
      setDetailLoading(true)
      const detail = await getMemoryGraphEdgeDetail(sourceToken, targetToken)
      setEdgeDetail(detail)
      setEvidenceGraph(toEvidenceGraphData(detail.evidence_graph))
      if (options?.locateInEvidence) {
        setViewMode('evidence')
      }
    } catch (error) {
      setSelectedEdgeData(null)
      setEdgeDetail(null)
      setEvidenceGraph({ nodes: [], edges: [] })
      setViewMode('entity')
      toast.error('加载关系详情失败', {
        description: error instanceof Error ? error.message : '未知错误',
      })
    } finally {
      setDetailLoading(false)
    }
  }, [graphData.edges, graphData.nodes])

  const openParagraphDetail = useCallback(async (
    paragraphHash: string,
    options?: { silent?: boolean },
  ): Promise<boolean> => {
    const cleanHash = String(paragraphHash || '').trim()
    if (!cleanHash) {
      return false
    }
    setSelectedNodeData(null)
    setSelectedEdgeData(null)
    setNodeDetail(null)
    setEdgeDetail(null)
    setSelectedRelationDetail(null)
    setSelectedRelationMetadata(null)
    try {
      setDetailLoading(true)
      const detail = await getMemoryGraphParagraphDetail(cleanHash)
      setEvidenceGraph(toEvidenceGraphData(detail.evidence_graph))
      setSelectedParagraphDetail(detail.paragraph)
      setSelectedParagraphMetadata({
        hash: detail.paragraph.hash,
        source: detail.paragraph.source,
        updated_at: detail.paragraph.updated_at,
        entity_count: detail.paragraph.entity_count,
        relation_count: detail.paragraph.relation_count,
        preview: detail.paragraph.preview,
      })
      setViewMode('evidence')
      return true
    } catch (error) {
      setEvidenceGraph({ nodes: [], edges: [] })
      setSelectedParagraphDetail(null)
      setSelectedParagraphMetadata(null)
      setViewMode('entity')
      if (!options?.silent) {
        toast.error('定位段落失败', {
          description: error instanceof Error ? error.message : '未能找到这段记忆',
        })
      }
      return false
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const restoreGraphTarget = useCallback(async (target: GraphRestoreTarget) => {
    if (target.type === 'entity') {
      await openNodeDetail(target.nodeId, { locateInEvidence: target.viewMode === 'evidence' })
      if (target.viewMode === 'entity') {
        setViewMode('entity')
      }
      return
    }
    if (target.type === 'edge') {
      await openEdgeDetail(target.source, target.target, { locateInEvidence: target.viewMode === 'evidence' })
      if (target.viewMode === 'entity') {
        setViewMode('entity')
      }
      return
    }
    if (target.type === 'paragraph') {
      const restored = await openParagraphDetail(target.paragraphHash, { silent: true })
      if (!restored) {
        toast.success('已刷新图谱', {
          description: '原段落已被删除，当前返回实体关系图。',
        })
      }
      return
    }
    setViewMode(target.viewMode)
  }, [openEdgeDetail, openNodeDetail, openParagraphDetail])

  const getCurrentRestoreTarget = useCallback((fallback?: GraphRestoreTarget): GraphRestoreTarget => {
    if (nodeDetail?.node.id) {
      return { type: 'entity', nodeId: nodeDetail.node.id, viewMode }
    }
    if (edgeDetail?.edge.source && edgeDetail.edge.target) {
      return { type: 'edge', source: edgeDetail.edge.source, target: edgeDetail.edge.target, viewMode }
    }
    if (selectedNodeData?.id) {
      return { type: 'entity', nodeId: selectedNodeData.id, viewMode }
    }
    if (selectedEdgeData?.source.id && selectedEdgeData.target.id) {
      return { type: 'edge', source: selectedEdgeData.source.id, target: selectedEdgeData.target.id, viewMode }
    }
    if (selectedParagraphDetail?.hash) {
      return { type: 'paragraph', paragraphHash: selectedParagraphDetail.hash, viewMode }
    }
    return fallback ?? { type: 'view', viewMode }
  }, [edgeDetail, nodeDetail, selectedEdgeData, selectedNodeData, selectedParagraphDetail, viewMode])

  useEffect(() => {
    const cleanHash = initialParagraphHash.trim()
    if (!cleanHash || cleanHash === appliedInitialParagraphHashRef.current) {
      return
    }
    // effect 内副作用——无需 rAF；标记用 ref（审核修复：rAF 冗余 + state→ref）
    appliedInitialParagraphHashRef.current = cleanHash
    void openParagraphDetail(cleanHash)
  }, [initialParagraphHash, openParagraphDetail])

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    void openNodeDetail(node.id)
  }, [openNodeDetail])

  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    void openEdgeDetail(edge.source, edge.target)
  }, [openEdgeDetail])

  const handleSearchResultClick = useCallback((item: MemoryGraphSearchItem) => {
    if (item.type === 'entity') {
      const entityName = String(item.entity_name ?? item.title ?? '').trim()
      if (!entityName) {
        return
      }
      void openNodeDetail(entityName, { locateInEvidence: true })
      return
    }
    const source = String(item.subject ?? '').trim()
    const target = String(item.object ?? '').trim()
    if (!source || !target) {
      toast.error('结果缺少定位信息', {
        description: '该关系记录没有可用的 subject/object，无法定位。',
      })
      return
    }
    void openEdgeDetail(source, target, { locateInEvidence: true })
  }, [openEdgeDetail, openNodeDetail])

  const handleEvidenceNodeClick = useCallback(async (_: React.MouseEvent, node: Node) => {
    const selected = evidenceGraph.nodes.find((item) => item.id === node.id)
    if (!selected) {
      return
    }

    if (selected.type === 'entity') {
      const entityName =
        String((selected.metadata as Record<string, unknown> | undefined)?.entity_name ?? '').trim() || selected.content
      try {
        setDetailLoading(true)
        const detail = await getMemoryGraphNodeDetail(entityName)
        setSelectedNodeData({
          id: detail.node.id,
          type: 'entity',
          content: detail.node.content,
          metadata: { hash: detail.node.hash },
        })
        setSelectedEdgeData(null)
        setNodeDetail(detail)
      } catch (error) {
        toast.error('加载实体详情失败', {
          description: error instanceof Error ? error.message : '未知错误',
        })
      } finally {
        setDetailLoading(false)
      }
      return
    }

    if (selected.type === 'relation') {
      const metadata = (selected.metadata ?? {}) as MemoryEvidenceRelationNodeMetadata
      const hash = String(metadata.hash ?? '').trim()
      const relation =
        allRelationDetails.find((item) => item.hash === hash) ?? buildRelationFromMetadata(metadata)
      setSelectedRelationMetadata(metadata)
      setSelectedRelationDetail(relation)
      setSelectedParagraphDetail(null)
      return
    }

    if (selected.type === 'paragraph') {
      const metadata = (selected.metadata ?? {}) as MemoryEvidenceParagraphNodeMetadata
      const hash = String(metadata.hash ?? '').trim()
      const paragraph =
        allParagraphDetails.find((item) => item.hash === hash) ?? buildParagraphFromMetadata(metadata)
      setSelectedParagraphMetadata(metadata)
      setSelectedParagraphDetail(paragraph)
      setSelectedRelationDetail(null)
    }
  }, [allParagraphDetails, allRelationDetails, evidenceGraph.nodes])

  const handleOpenNodeEvidence = useCallback(() => {
    setViewMode('evidence')
    setSelectedNodeData(null)
  }, [])

  const handleOpenEdgeEvidence = useCallback(() => {
    setViewMode('evidence')
    setSelectedEdgeData(null)
  }, [])

  return {
    loading,
    nodeLimit,
    setNodeLimit,
    searchInput,
    setSearchInput,
    searchLoading,
    searchResults,
    searchFallbackMode,
    appliedSearchQuery,
    viewMode,
    setViewMode,
    graphData,
    evidenceGraph,
    stats,
    detailLoading,
    selectedNodeData,
    setSelectedNodeData,
    selectedEdgeData,
    setSelectedEdgeData,
    nodeDetail,
    edgeDetail,
    selectedRelationDetail,
    setSelectedRelationDetail,
    selectedRelationMetadata,
    setSelectedRelationMetadata,
    selectedParagraphDetail,
    setSelectedParagraphDetail,
    selectedParagraphMetadata,
    setSelectedParagraphMetadata,
    loadGraph,
    handleSearch,
    handleNodeClick,
    handleEdgeClick,
    handleSearchResultClick,
    handleEvidenceNodeClick,
    handleOpenNodeEvidence,
    handleOpenEdgeEvidence,
    restoreGraphTarget,
    getCurrentRestoreTarget,
  }
}
