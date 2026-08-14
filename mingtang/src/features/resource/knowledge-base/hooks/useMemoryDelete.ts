/**
 * useMemoryDelete —— 长期记忆「删除与恢复」领域 hook（页面逻辑下沉切片）。
 *
 * 收编删除相关的服务端状态与交互：
 * - 来源列表（sources）与删除操作列表（operations）走 useQuery，仅在删除面板激活时拉取（enabled: active）；
 * - 操作列表搜索/筛选/分页、操作详情、源选择仍以本地 state + 命令式/effect 维持
 *   （这些不是标准 {items,total} 服务端分页，保留原命令式分页态，以最小行为变化为准）；
 * - 删除预览-执行用 usePendingOperation：openSourceDeletePreview 暂存待删请求并打开对话框，
 *   随后拉预览（setDeletePreview）；对话框 onExecute → confirm → onConfirm 执行 executeMemoryDelete；
 * - 删除/恢复成功后刷新来源与操作列表。
 *
 * 读失败原由 loadDeletePanel 弹 toast；迁移后查询读失败按 query.ts 约定不弹全局 toast，由 deleteErrorText
 *   局部呈现；写操作（执行/恢复）保留原中文 toast 文案，预览/执行错误写入 deletePreviewError。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { toast } from 'sonner'
import { useClientSideList } from '@/hooks/useClientSideList'
import { usePendingOperation } from '@/hooks/usePendingOperation'
import {
  executeMemoryDelete,
  getMemoryDeleteOperation,
  getMemoryDeleteOperations,
  getMemorySources,
  previewMemoryDelete,
  restoreMemoryDelete,
  type MemoryDeleteExecutePayload,
  type MemoryDeleteOperationPayload,
  type MemoryDeleteRequestPayload,
  type MemorySourceItemPayload,
} from '@/lib/memory-api'

import { DELETE_OPERATION_FETCH_LIMIT, DELETE_OPERATION_ITEM_PAGE_SIZE, DELETE_OPERATION_PAGE_SIZE } from '../constants'
import type { DeleteOperationItem } from '../utils'

/** 删除操作列表的客户端筛选状态（useClientSideList 的 filters 形状；引用变化即筛选变化） */
interface DeleteOperationFilters {
  search: string
  mode: string
  status: string
}

/** 删除操作列表过滤：搜索 + 模式/状态筛选（与旧实现逐字一致） */
function filterDeleteOperations(
  operations: MemoryDeleteOperationPayload[],
  filters: DeleteOperationFilters,
): MemoryDeleteOperationPayload[] {
  const keyword = filters.search.trim().toLowerCase()
  return operations.filter((operation) => {
    const mode = String(operation.mode ?? '').trim()
    const status = String(operation.status ?? '').trim()
    const summary = operation.summary ?? {}
    const sources = Array.isArray(summary.sources) ? summary.sources : []

    if (filters.mode !== 'all' && mode !== filters.mode) {
      return false
    }
    if (filters.status !== 'all' && status !== filters.status) {
      return false
    }
    if (!keyword) {
      return true
    }

    return [
      operation.operation_id,
      operation.reason,
      operation.requested_by,
      mode,
      status,
      ...sources.map((item) => String(item)),
    ]
      .map((item) => String(item ?? '').toLowerCase())
      .some((item) => item.includes(keyword))
  })
}

function getDeleteOperationId(operation: MemoryDeleteOperationPayload): string {
  return operation.operation_id
}

/** 选中操作影响对象列表的客户端筛选状态（selectionId 只用于触发页码重置，不参与过滤） */
interface DeleteOperationItemFilters {
  selectionId: string
  search: string
}

/** 选中操作影响对象过滤：item_type / hash / item_key / 载荷 source 关键词（与旧实现逐字一致） */
function filterDeleteOperationItems(
  items: DeleteOperationItem[],
  filters: DeleteOperationItemFilters,
): DeleteOperationItem[] {
  const keyword = filters.search.trim().toLowerCase()
  if (!keyword) {
    return items
  }
  return items.filter((item) => {
    const payload = item.payload ?? {}
    const source = String(payload.source ?? '').trim()
    return [
      item.item_type,
      item.item_hash,
      item.item_key,
      source,
    ]
      .map((value) => String(value ?? '').toLowerCase())
      .some((value) => value.includes(keyword))
  })
}

function getDeleteOperationItemId(item: DeleteOperationItem): string {
  return `${item.item_type}:${item.item_hash}:${item.item_key ?? ''}`
}

export interface UseMemoryDeleteOptions {
  /** 删除面板是否激活；非激活时不拉取来源/操作列表，不加载操作详情 */
  active: boolean
  /** 深链接初始值：来源搜索框 */
  initialSourceSearch?: string
  /** 深链接初始值：操作搜索框 */
  initialOperationSearch?: string
  /** 深链接初始值：选中操作 ID */
  initialOperationId?: string
  /** 深链接初始值：操作影响对象搜索框 */
  initialItemSearch?: string
}

export interface UseMemoryDeleteResult {
  sourceSearch: string
  setSourceSearch: React.Dispatch<React.SetStateAction<string>>
  selectedSources: string[]
  setSelectedSources: React.Dispatch<React.SetStateAction<string[]>>
  filteredSources: MemorySourceItemPayload[]
  openSourceDeletePreview: () => Promise<void>
  toggleSourceSelection: (source: string, checked: boolean) => void
  /** 仅刷新来源列表（供纠错回退等外部写操作后同步） */
  refreshSources: () => Promise<void>

  operationSearch: string
  setOperationSearch: React.Dispatch<React.SetStateAction<string>>
  operationModeFilter: string
  setOperationModeFilter: React.Dispatch<React.SetStateAction<string>>
  operationStatusFilter: string
  setOperationStatusFilter: React.Dispatch<React.SetStateAction<string>>
  filteredDeleteOperations: MemoryDeleteOperationPayload[]
  deleteOperations: MemoryDeleteOperationPayload[]
  operationPage: number
  setOperationPage: React.Dispatch<React.SetStateAction<number>>
  deleteOperationPageCount: number
  pagedDeleteOperations: MemoryDeleteOperationPayload[]
  selectedDeleteOperation: MemoryDeleteOperationPayload | null
  setSelectedOperationId: React.Dispatch<React.SetStateAction<string | null>>
  restoreDeleteOperation: (operationId: string) => Promise<void>
  deleteRestoring: boolean
  selectedOperationCounts: Record<string, number>
  selectedOperationDetailLoading: boolean
  selectedOperationDetailError: string
  selectedOperationSources: string[]
  selectedOperationItems: DeleteOperationItem[]
  filteredSelectedOperationItems: DeleteOperationItem[]
  selectedOperationItemSearch: string
  setSelectedOperationItemSearch: React.Dispatch<React.SetStateAction<string>>
  selectedOperationItemPage: number
  setSelectedOperationItemPage: React.Dispatch<React.SetStateAction<number>>
  selectedOperationItemPageCount: number
  pagedSelectedOperationItems: DeleteOperationItem[]

  // 删除对话框（MemoryDeleteDialog）相关
  deleteDialogOpen: boolean
  closeDeleteDialog: (open: boolean) => void
  deleteDialogTitle: string
  deleteDialogDescription: string
  deletePreview: Awaited<ReturnType<typeof previewMemoryDelete>> | null
  deletePreviewError: string | null
  deletePreviewLoading: boolean
  deleteExecuting: boolean
  deleteResult: MemoryDeleteExecutePayload | null
  executePendingDelete: () => Promise<void>

  /** 删除数据读取错误文案（查询失败时局部呈现） */
  deleteErrorText: string
}

export function useMemoryDelete({
  active,
  initialSourceSearch = '',
  initialOperationSearch = '',
  initialOperationId = '',
  initialItemSearch = '',
}: UseMemoryDeleteOptions): UseMemoryDeleteResult {
  // 来源列表 / 删除操作列表：仅在删除面板激活时拉取
  const sourcesQuery = useQuery({
    queryKey: ['memory-delete', 'sources'],
    queryFn: () => getMemorySources(),
    enabled: active,
  })
  const operationsQuery = useQuery({
    queryKey: ['memory-delete', 'operations'],
    queryFn: () => getMemoryDeleteOperations(DELETE_OPERATION_FETCH_LIMIT),
    enabled: active,
  })

  const memorySources = useMemo(() => sourcesQuery.data?.items ?? [], [sourcesQuery.data?.items])
  const deleteOperations = useMemo(() => operationsQuery.data?.items ?? [], [operationsQuery.data?.items])

  const deleteError = sourcesQuery.error ?? operationsQuery.error
  const deleteErrorText = deleteError
    ? deleteError instanceof Error
      ? deleteError.message
      : '加载删除数据失败'
    : ''

  const refreshDeleteData = useCallback(async () => {
    await Promise.all([sourcesQuery.refetch(), operationsQuery.refetch()])
  }, [operationsQuery, sourcesQuery])

  // 仅刷新来源列表：供外部领域（如纠错回退）在写操作后同步来源，原页面回退时只重拉 sources
  const refreshSources = useCallback(async () => {
    await sourcesQuery.refetch()
  }, [sourcesQuery])

  const [sourceSearch, setSourceSearch] = useState(initialSourceSearch)
  const [operationSearch, setOperationSearch] = useState(initialOperationSearch)
  const [operationModeFilter, setOperationModeFilter] = useState('all')
  const [operationStatusFilter, setOperationStatusFilter] = useState('all')
  const [selectedOperationItemSearch, setSelectedOperationItemSearch] = useState(initialItemSearch)
  const [selectedSources, setSelectedSources] = useState<string[]>([])

  const [selectedOperationDetail, setSelectedOperationDetail] = useState<MemoryDeleteOperationPayload | null>(null)
  const [selectedOperationDetailLoading, setSelectedOperationDetailLoading] = useState(false)
  const [selectedOperationDetailError, setSelectedOperationDetailError] = useState('')

  // 删除对话框业务态（预览/结果/执行）；待删请求由 usePendingOperation 持有。
  // dialogOpen 独立于待定态：执行成功后对话框需保持打开以展示恢复入口，故不复用 isWaiting。
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteDialogTitle, setDeleteDialogTitle] = useState('删除预览')
  const [deleteDialogDescription, setDeleteDialogDescription] = useState('')
  const [deletePreview, setDeletePreview] = useState<Awaited<ReturnType<typeof previewMemoryDelete>> | null>(null)
  const [deletePreviewError, setDeletePreviewError] = useState<string | null>(null)
  const [deletePreviewLoading, setDeletePreviewLoading] = useState(false)
  const [deleteExecuting, setDeleteExecuting] = useState(false)
  const [deleteRestoring, setDeleteRestoring] = useState(false)
  const [deleteResult, setDeleteResult] = useState<MemoryDeleteExecutePayload | null>(null)

  const filteredSources = useMemo(() => {
    const keyword = sourceSearch.trim().toLowerCase()
    if (!keyword) {
      return memorySources
    }
    return memorySources.filter((item) => String(item.source ?? '').toLowerCase().includes(keyword))
  }, [memorySources, sourceSearch])

  const operationFilters = useMemo(
    () => ({ search: operationSearch, mode: operationModeFilter, status: operationStatusFilter }),
    [operationModeFilter, operationSearch, operationStatusFilter],
  )
  const operationList = useClientSideList({
    items: deleteOperations,
    filters: operationFilters,
    pageSize: DELETE_OPERATION_PAGE_SIZE,
    filter: filterDeleteOperations,
    getId: getDeleteOperationId,
    initialSelectedId: initialOperationId || null,
  })

  const filteredDeleteOperations = operationList.filtered
  const deleteOperationPageCount = operationList.totalPages
  const pagedDeleteOperations = operationList.paged
  const operationPage = operationList.page
  const setOperationPage = operationList.setPage
  const selectedOperationId = operationList.selectedId
  const setSelectedOperationId = operationList.setSelectedId

  // 选中操作展示：过滤结果按 id 命中 → 深链接 stub（id 尚不在列表时先占位，详情异步加载）→ 当前页首项
  const selectedDeleteOperation = useMemo<MemoryDeleteOperationPayload | null>(() => {
    if (operationList.selectedItem) {
      return operationList.selectedItem
    }
    if (operationList.selectedId) {
      return {
        operation_id: operationList.selectedId,
        mode: '',
        status: '',
      } satisfies MemoryDeleteOperationPayload
    }
    return operationList.paged[0] ?? null
  }, [operationList.paged, operationList.selectedId, operationList.selectedItem])

  useEffect(() => {
    if (!active) {
      return
    }
    const operationId = selectedDeleteOperation?.operation_id
    if (!operationId) {
      return
    }

    let cancelled = false
    void (async () => {
      setSelectedOperationDetailLoading(true)
      setSelectedOperationDetailError('')
      try {
        const payload = await getMemoryDeleteOperation(operationId)
        if (cancelled) {
          return
        }
        if (payload.error || !payload.operation) {
          setSelectedOperationDetail(null)
          setSelectedOperationDetailError(payload.error || '未能加载删除操作详情')
          return
        }
        setSelectedOperationDetail(payload.operation)
      } catch (error) {
        if (cancelled) {
          return
        }
        setSelectedOperationDetail(null)
        setSelectedOperationDetailError(error instanceof Error ? error.message : '未能加载删除操作详情')
      } finally {
        if (!cancelled) {
          setSelectedOperationDetailLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [active, selectedDeleteOperation?.operation_id])

  const toggleSourceSelection = useCallback((source: string, checked: boolean) => {
    setSelectedSources((current) => {
      if (checked) {
        return current.includes(source) ? current : [...current, source]
      }
      return current.filter((item) => item !== source)
    })
  }, [])

  // 删除预览-执行：用通用待定模块缓冲「预览 → 对话框确认 → 执行」
  const pendingOp = usePendingOperation<MemoryDeleteRequestPayload>({
    onConfirm: async (request) => {
      try {
        setDeleteExecuting(true)
        const result = await executeMemoryDelete(request)
        setDeleteResult(result)
        if (!result.error) {
          toast.success(`操作 ${result.operation_id} 已完成`)
        } else {
          toast.error(result.error || '未能执行删除')
        }
        if (!result.error) {
          await refreshDeleteData()
          setSelectedSources([])
        }
      } catch (error) {
        setDeletePreviewError(error instanceof Error ? error.message : '删除失败')
        toast.error(error instanceof Error ? error.message : '未知错误')
      } finally {
        setDeleteExecuting(false)
      }
    },
  })

  const openSourceDeletePreview = useCallback(async () => {
    if (selectedSources.length <= 0) {
      toast.error('至少选择一个来源后再进行删除预览')
      return
    }
    const request: MemoryDeleteRequestPayload = {
      mode: 'source',
      selector: { sources: selectedSources },
      reason: 'knowledge_base_source_delete',
      requested_by: 'knowledge_base',
    }
    setDeleteDialogTitle('批量删除来源')
    setDeleteDialogDescription('删除来源只会删除该来源下的段落，以及失去全部证据的关系，不会自动删除实体')
    setDeletePreview(null)
    setDeleteResult(null)
    setDeletePreviewError(null)
    // 暂存待删请求并打开对话框，随后异步拉取预览
    pendingOp.submit(request)
    setDeleteDialogOpen(true)
    setDeletePreviewLoading(true)
    try {
      const preview = await previewMemoryDelete(request)
      setDeletePreview(preview)
    } catch (error) {
      setDeletePreviewError(error instanceof Error ? error.message : '删除预览失败')
    } finally {
      setDeletePreviewLoading(false)
    }
  }, [pendingOp, selectedSources])

  const executePendingDelete = useCallback(async () => {
    await pendingOp.confirm()
  }, [pendingOp])

  const restoreDeleteOperation = useCallback(async (operationId: string) => {
    try {
      setDeleteRestoring(true)
      await restoreMemoryDelete({ operation_id: operationId, requested_by: 'knowledge_base' })
      toast.success(`删除操作 ${operationId} 已恢复`)
      setDeleteDialogOpen(false)
      pendingOp.cancel()
      setDeletePreview(null)
      setDeleteResult(null)
      setDeletePreviewError(null)
      await refreshDeleteData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '未知错误')
    } finally {
      setDeleteRestoring(false)
    }
  }, [pendingOp, refreshDeleteData])

  const closeDeleteDialog = useCallback((open: boolean) => {
    if (!open) {
      setDeleteDialogOpen(false)
      pendingOp.cancel()
      setDeletePreview(null)
      setDeleteResult(null)
      setDeletePreviewError(null)
      return
    }
    setDeleteDialogOpen(true)
  }, [pendingOp])

  const selectedOperationResolved = useMemo(() => {
    if (!selectedDeleteOperation) {
      return null
    }
    if (selectedOperationDetail?.operation_id === selectedDeleteOperation.operation_id) {
      return {
        ...selectedDeleteOperation,
        ...selectedOperationDetail,
      } satisfies MemoryDeleteOperationPayload
    }
    return selectedDeleteOperation
  }, [selectedDeleteOperation, selectedOperationDetail])

  const selectedOperationSummaryResolved = (selectedOperationResolved?.summary ?? {}) as Record<string, unknown>
  const selectedOperationCounts = (selectedOperationSummaryResolved.counts as Record<string, number> | undefined) ?? {}
  const selectedOperationSources = Array.isArray(selectedOperationSummaryResolved.sources)
    ? selectedOperationSummaryResolved.sources.map((item) => String(item)).filter(Boolean)
    : []
  // 用 useMemo 稳定数组引用，避免每次渲染产生新数组而触发下游 useMemo 失效（exhaustive-deps）
  const selectedOperationItems = useMemo(
    () => (Array.isArray(selectedOperationResolved?.items) ? selectedOperationResolved.items : []),
    [selectedOperationResolved],
  )
  const itemFilters = useMemo(
    () => ({ selectionId: selectedOperationId ?? '', search: selectedOperationItemSearch }),
    [selectedOperationId, selectedOperationItemSearch],
  )
  const itemList = useClientSideList({
    items: selectedOperationItems,
    filters: itemFilters,
    pageSize: DELETE_OPERATION_ITEM_PAGE_SIZE,
    filter: filterDeleteOperationItems,
    getId: getDeleteOperationItemId,
  })

  const filteredSelectedOperationItems = itemList.filtered
  const selectedOperationItemPageCount = itemList.totalPages
  const pagedSelectedOperationItems = itemList.paged
  const selectedOperationItemPage = itemList.page
  const setSelectedOperationItemPage = itemList.setPage

  return {
    sourceSearch,
    setSourceSearch,
    selectedSources,
    setSelectedSources,
    filteredSources,
    openSourceDeletePreview,
    toggleSourceSelection,
    refreshSources,
    operationSearch,
    setOperationSearch,
    operationModeFilter,
    setOperationModeFilter,
    operationStatusFilter,
    setOperationStatusFilter,
    filteredDeleteOperations,
    deleteOperations,
    operationPage,
    setOperationPage,
    deleteOperationPageCount,
    pagedDeleteOperations,
    selectedDeleteOperation,
    setSelectedOperationId,
    restoreDeleteOperation,
    deleteRestoring,
    selectedOperationCounts,
    selectedOperationDetailLoading,
    selectedOperationDetailError,
    selectedOperationSources,
    selectedOperationItems,
    filteredSelectedOperationItems,
    selectedOperationItemSearch,
    setSelectedOperationItemSearch,
    selectedOperationItemPage,
    setSelectedOperationItemPage,
    selectedOperationItemPageCount,
    pagedSelectedOperationItems,
    deleteDialogOpen,
    closeDeleteDialog,
    deleteDialogTitle,
    deleteDialogDescription,
    deletePreview,
    deletePreviewError,
    deletePreviewLoading,
    deleteExecuting,
    deleteResult,
    executePendingDelete,
    deleteErrorText,
  }
}
