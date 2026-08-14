/**
 * useGraphDelete —— 记忆图谱「删除预览-执行-恢复」领域 hook（R3 遗留 D6：P2-B 从 knowledge-graph.tsx 迁出）。
 *
 * 收编删除相关的状态与交互，复用通用 usePendingOperation（与 knowledge-base 的 useMemoryDelete 同构）：
 * - openDeleteDialog 暂存待删请求（pendingOp.submit）并打开 MemoryDeleteDialog、异步拉取预览；
 * - 对话框 onExecute → executeCurrentDelete → pendingOp.confirm() 执行 executeMemoryDelete；
 * - 执行/恢复成功后刷新图谱并按 restoreTarget 恢复视图位置。
 *
 * 依赖的图谱状态（nodeDetail/edgeDetail/viewMode 与 loadGraph/restoreGraphTarget 等）由
 * 父组件从 useGraphExplorer 传入——本 hook 不重复持有图谱数据。
 */
import { useCallback, useState } from 'react'

import { toast } from 'sonner'

import { usePendingOperation } from '@/hooks/usePendingOperation'
import {
  executeMemoryDelete,
  previewMemoryDelete,
  restoreMemoryDelete,
  type MemoryDeleteExecutePayload,
  type MemoryDeleteRequestPayload,
  type MemoryGraphEdgeDetailPayload,
  type MemoryGraphNodeDetailPayload,
  type MemoryGraphParagraphDetailPayload,
  type MemoryGraphRelationDetailPayload,
} from '@/lib/memory-api'

import type { GraphRestoreTarget, GraphViewMode } from './use-graph-explorer'

/** 删除草稿：对话框内容 + 待删请求 + 删除后恢复目标 */
export type DeleteDraft = {
  title: string
  description: string
  request: MemoryDeleteRequestPayload
  restoreTarget: GraphRestoreTarget
}

export interface UseGraphDeleteOptions {
  nodeDetail: MemoryGraphNodeDetailPayload | null
  edgeDetail: MemoryGraphEdgeDetailPayload | null
  viewMode: GraphViewMode
  /** 当前选中态 → 恢复目标（删除成功后回到原视图位置） */
  getCurrentRestoreTarget: (fallback?: GraphRestoreTarget) => GraphRestoreTarget
  /** 刷新图谱（删除/恢复成功后同步） */
  loadGraph: (options?: { silent?: boolean; keepSelection?: boolean }) => Promise<void>
  /** 按目标恢复视图位置 */
  restoreGraphTarget: (target: GraphRestoreTarget) => Promise<void>
}

export function useGraphDelete({
  nodeDetail,
  edgeDetail,
  viewMode,
  getCurrentRestoreTarget,
  loadGraph,
  restoreGraphTarget,
}: UseGraphDeleteOptions) {
  const [deleteDraft, setDeleteDraft] = useState<DeleteDraft | null>(null)
  const [deletePreviewLoading, setDeletePreviewLoading] = useState(false)
  const [deletePreviewError, setDeletePreviewError] = useState<string | null>(null)
  const [deleteResult, setDeleteResult] = useState<MemoryDeleteExecutePayload | null>(null)
  const [deleteExecuting, setDeleteExecuting] = useState(false)
  const [deleteRestoring, setDeleteRestoring] = useState(false)
  const [deletePreview, setDeletePreview] = useState<Awaited<ReturnType<typeof previewMemoryDelete>> | null>(null)

  // 删除预览-执行：用通用待定模块缓冲「预览 → 对话框确认 → 执行」；
  // onConfirm 内部吞掉所有错误（写错误进 deletePreviewError），成功后由 confirm() 清空待定。
  const pendingOp = usePendingOperation<MemoryDeleteRequestPayload>({
    onConfirm: async (request) => {
      try {
        setDeleteExecuting(true)
        const result = await executeMemoryDelete(request)
        setDeleteResult(result)
        if (!result.error) {
          toast.success('删除成功', {
            description: `操作 ${result.operation_id} 已完成`,
          })
        } else {
          toast.error('删除失败', {
            description: result.error || '未能执行删除',
          })
        }
        if (!result.error) {
          await loadGraph({ silent: true, keepSelection: true })
          await restoreGraphTarget(deleteDraft?.restoreTarget ?? { type: 'view', viewMode })
        }
      } catch (error) {
        setDeletePreviewError(error instanceof Error ? error.message : '删除失败')
        toast.error('删除失败', {
          description: error instanceof Error ? error.message : '未知错误',
        })
      } finally {
        setDeleteExecuting(false)
      }
    },
  })

  const openDeleteDialog = useCallback(async (draft: DeleteDraft) => {
    setDeleteDraft(draft)
    setDeletePreview(null)
    setDeleteResult(null)
    setDeletePreviewError(null)
    // 暂存待删请求并进入等待态，随后异步拉取预览
    pendingOp.submit(draft.request)
    setDeletePreviewLoading(true)
    try {
      const preview = await previewMemoryDelete(draft.request)
      setDeletePreview(preview)
    } catch (error) {
      setDeletePreviewError(error instanceof Error ? error.message : '删除预览失败')
    } finally {
      setDeletePreviewLoading(false)
    }
  }, [pendingOp])

  const closeDeleteDialog = useCallback((open: boolean) => {
    if (!open) {
      setDeleteDraft(null)
      setDeletePreview(null)
      setDeleteResult(null)
      setDeletePreviewError(null)
      pendingOp.cancel()
    }
  }, [pendingOp])

  const executeCurrentDelete = useCallback(async () => {
    await pendingOp.confirm()
  }, [pendingOp])

  const restoreCurrentDelete = useCallback(async () => {
    if (!deleteResult?.operation_id) {
      return
    }
    try {
      setDeleteRestoring(true)
      await restoreMemoryDelete({
        operation_id: deleteResult.operation_id,
        requested_by: 'knowledge_graph',
      })
      toast.success('恢复成功', {
        description: `删除操作 ${deleteResult.operation_id} 已恢复`,
      })
      const restoreTarget = deleteDraft?.restoreTarget ?? getCurrentRestoreTarget()
      closeDeleteDialog(false)
      await loadGraph({ silent: true, keepSelection: true })
      await restoreGraphTarget(restoreTarget)
    } catch (error) {
      toast.error('恢复失败', {
        description: error instanceof Error ? error.message : '未知错误',
      })
    } finally {
      setDeleteRestoring(false)
    }
  }, [closeDeleteDialog, deleteDraft, deleteResult, getCurrentRestoreTarget, loadGraph, restoreGraphTarget])

  const requestDeleteEntity = useCallback(({ includeParagraphs }: { includeParagraphs: boolean }) => {
    const entityHash = String(nodeDetail?.node.hash ?? '').trim()
    if (!entityHash) {
      toast.error('缺少实体标识', {
        description: '当前实体没有可用的 hash，无法执行删除。',
      })
      return
    }
    void openDeleteDialog({
      title: '删除实体',
      description: '将删除该实体，并自动包含与该实体关联的关系。可按需额外删除支撑段落。',
      restoreTarget: getCurrentRestoreTarget({
        type: 'entity',
        nodeId: String(nodeDetail?.node.id ?? nodeDetail?.node.content ?? ''),
        viewMode,
      }),
      request: {
        mode: 'mixed',
        selector: {
          entity_hashes: [entityHash],
          paragraph_hashes: includeParagraphs ? (nodeDetail?.paragraphs ?? []).map((item) => item.hash) : [],
        },
        reason: 'knowledge_graph_delete_entity',
        requested_by: 'knowledge_graph',
      },
    })
  }, [getCurrentRestoreTarget, nodeDetail, openDeleteDialog, viewMode])

  const requestDeleteEdgeGroup = useCallback(({ includeParagraphs }: { includeParagraphs: boolean }) => {
    const relationHashes = edgeDetail?.edge.relation_hashes ?? []
    if (relationHashes.length <= 0) {
      toast.error('缺少关系标识', {
        description: '当前关系组没有可用的 relation hash。',
      })
      return
    }
    void openDeleteDialog({
      title: '删除关系组',
      description: '将删除这条聚合边对应的全部关系。可按需额外删除支撑段落。',
      restoreTarget: getCurrentRestoreTarget({
        type: 'edge',
        source: String(edgeDetail?.edge.source ?? ''),
        target: String(edgeDetail?.edge.target ?? ''),
        viewMode,
      }),
      request: {
        mode: 'mixed',
        selector: {
          relation_hashes: relationHashes,
          paragraph_hashes: includeParagraphs ? (edgeDetail?.paragraphs ?? []).map((item) => item.hash) : [],
        },
        reason: 'knowledge_graph_delete_edge_group',
        requested_by: 'knowledge_graph',
      },
    })
  }, [edgeDetail, getCurrentRestoreTarget, openDeleteDialog, viewMode])

  const requestDeleteRelation = useCallback(
    (relation: MemoryGraphRelationDetailPayload, includeParagraphs = false) => {
      void openDeleteDialog({
        title: '删除关系',
        description: includeParagraphs ? '将删除这条关系及其支撑段落。' : '将只删除这条关系，保留段落证据。',
        restoreTarget: getCurrentRestoreTarget({ type: 'view', viewMode }),
        request: {
          mode: 'mixed',
          selector: {
            relation_hashes: [relation.hash],
            paragraph_hashes: includeParagraphs ? relation.paragraph_hashes : [],
          },
          reason: 'knowledge_graph_delete_relation',
          requested_by: 'knowledge_graph',
        },
      })
    },
    [getCurrentRestoreTarget, openDeleteDialog, viewMode],
  )

  const requestDeleteParagraph = useCallback((paragraph: MemoryGraphParagraphDetailPayload) => {
    void openDeleteDialog({
      title: '删除段落证据',
      description: '将删除这段证据，并自动删除失去全部证据的关系。',
      restoreTarget: getCurrentRestoreTarget({
        type: 'paragraph',
        paragraphHash: paragraph.hash,
        viewMode,
      }),
      request: {
        mode: 'mixed',
        selector: {
          paragraph_hashes: [paragraph.hash],
        },
        reason: 'knowledge_graph_delete_paragraph',
        requested_by: 'knowledge_graph',
      },
    })
  }, [getCurrentRestoreTarget, openDeleteDialog, viewMode])

  return {
    deleteDraft,
    deletePreview,
    deletePreviewError,
    deletePreviewLoading,
    deleteExecuting,
    deleteRestoring,
    deleteResult,
    openDeleteDialog,
    closeDeleteDialog,
    executeCurrentDelete,
    restoreCurrentDelete,
    requestDeleteEntity,
    requestDeleteEdgeGroup,
    requestDeleteRelation,
    requestDeleteParagraph,
  }
}
