/**
 * useClientSideList —— 对「客户端全量数组」的过滤 / 分页 / 单选状态机（客户端过滤版）。
 *
 * 与 useDataList（服务端查询驱动版）的分工：
 * - useDataList：数据在服务端，内部发起列表查询，queryKey 从分页/搜索/筛选派生，参数变化自动重新拉取
 *   （服务端分页——items 只是当前页，total 来自响应）；
 * - useClientSideList：数据已全部在内存（useQuery/useMemo 的结果），不发任何查询，
 *   只负责「过滤 → 分页 → 选中对齐」的本地状态机（客户端分页——items 是全量数组）。
 *
 * 收编的「状态自管理列表」规则（原 5 处手抄，本 hook 一处实现）：
 * - 筛选变化（filters 引用变化）→ 渲染期自动重置页码到 1 并清空选中（React 官方「渲染期调整状态」模式，
 *   无 effect、无 rAF——顺带消除 memory-delete-dialog 的 rAF 规避）；
 * - 页码超界（筛选未变、数据变少）→ 渲染期自动回拉到末页；
 * - 选中项落空（selectedId 在过滤结果中不存在）→ selectedItem 为 null，回退展示由调用方决定
 *   （如深链接 stub / 当前页首项）；
 * - setPage 钳制到 [1, totalPages]，支持函数式更新（页码不会越界）。
 *
 * 调用方约定：
 * - filters 需用 useMemo 稳定引用——引用变化即「筛选变化」；
 * - filter 建议模块级纯函数（引用稳定，避免每次渲染重算过滤结果）。
 */
import { useCallback, useMemo, useState } from 'react'

export interface UseClientSideListConfig<TItem, TFilters, TId> {
  /** 全量数据（未过滤）——通常来自 useQuery/useMemo 的结果 */
  items: TItem[]
  /** 筛选状态；引用变化视为筛选变化 → 自动重置页码并清空选中 */
  filters: TFilters
  /** 每页条数 */
  pageSize: number
  /** 过滤函数：items + filters → 过滤后数组 */
  filter: (items: TItem[], filters: TFilters) => TItem[]
  /** 从行取 id，用于选中对齐 */
  getId: (item: TItem) => TId
  /** 初始页码，默认 1 */
  initialPage?: number
  /** 初始选中 id（深链接场景），默认 null */
  initialSelectedId?: TId | null
}

export interface UseClientSideListResult<TItem, TId> {
  /** 过滤后的全量（未分页） */
  filtered: TItem[]
  /** 当前页切片（页码已钳制，切片不会越界） */
  paged: TItem[]
  /** 总页数（至少 1） */
  totalPages: number
  /** 当前页码（筛选变化时重置为 1；数据变少时回拉到末页） */
  page: number
  /** 翻页（支持函数式更新；钳制到 [1, totalPages]） */
  setPage: React.Dispatch<React.SetStateAction<number>>
  /** 当前选中 id（筛选变化时清空） */
  selectedId: TId | null
  /** 选中项（按 id 在过滤结果中匹配；落空时为 null，由调用方决定回退展示） */
  selectedItem: TItem | null
  /** 选中 / 清空选中 */
  setSelectedId: React.Dispatch<React.SetStateAction<TId | null>>
}

export function useClientSideList<TItem, TFilters, TId>({
  items,
  filters,
  pageSize,
  filter,
  getId,
  initialPage = 1,
  initialSelectedId = null,
}: UseClientSideListConfig<TItem, TFilters, TId>): UseClientSideListResult<TItem, TId> {
  const [page, setPageRaw] = useState(initialPage)
  const [selectedId, setSelectedIdRaw] = useState<TId | null>(initialSelectedId)
  const [prevFilters, setPrevFilters] = useState(filters)

  const filtered = useMemo(() => filter(items, filters), [filter, filters, items])
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))

  // 筛选变化 → 重置页码 + 清空选中（渲染期调整状态——React 官方模式，无 effect/rAF）
  if (prevFilters !== filters) {
    setPrevFilters(filters)
    setPageRaw(1)
    setSelectedIdRaw(null)
  } else if (page > totalPages) {
    // 页码超界（筛选未变、数据变少）→ 回拉到末页（渲染期调整状态）
    setPageRaw(totalPages)
  }

  const paged = useMemo(() => {
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [filtered, page, pageSize])

  const selectedItem = useMemo(() => {
    if (selectedId === null) {
      return null
    }
    return filtered.find((item) => getId(item) === selectedId) ?? null
  }, [filtered, getId, selectedId])

  const setPage = useCallback(
    (updater: React.SetStateAction<number>) => {
      setPageRaw((current) => {
        const next = typeof updater === 'function' ? (updater as (prev: number) => number)(current) : updater
        const clamped = Math.min(Math.max(1, Math.trunc(next)), totalPages)
        return Number.isFinite(clamped) ? clamped : current
      })
    },
    [totalPages],
  )

  return {
    filtered,
    paged,
    totalPages,
    page,
    setPage,
    selectedId,
    selectedItem,
    setSelectedId: setSelectedIdRaw,
  }
}
