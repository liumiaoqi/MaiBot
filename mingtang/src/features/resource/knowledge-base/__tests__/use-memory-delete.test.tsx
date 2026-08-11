/**
 * useMemoryDelete hook 测试（R4-2-7）
 *
 * 核心验证：
 * - 来源/操作列表仅在 active 时拉取（enabled: active 门控）
 * - 删除预览-执行：openSourceDeletePreview → previewMemoryDelete → executePendingDelete → executeMemoryDelete + toast.success
 * - 恢复：restoreDeleteOperation → restoreMemoryDelete + toast.success
 * - 读失败局部呈现（deleteErrorText）
 * - 写失败 toast.error
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

vi.mock('@/lib/memory-api', () => ({
  getMemorySources: vi.fn(),
  getMemoryDeleteOperations: vi.fn(),
  getMemoryDeleteOperation: vi.fn(),
  previewMemoryDelete: vi.fn(),
  executeMemoryDelete: vi.fn(),
  restoreMemoryDelete: vi.fn(),
}))

import {
  executeMemoryDelete,
  getMemoryDeleteOperation,
  getMemoryDeleteOperations,
  getMemorySources,
  previewMemoryDelete,
  restoreMemoryDelete,
} from '@/lib/memory-api'
import { useMemoryDelete } from '../hooks/useMemoryDelete'

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'QueryWrapper'
  return Wrapper
}

const mockSources = {
  items: [
    { source: 'src1', paragraph_count: 10 },
    { source: 'src2', paragraph_count: 5 },
  ],
  count: 2,
}

const mockOperations = {
  items: [
    {
      operation_id: 'op1',
      mode: 'source',
      status: 'completed',
      summary: { counts: { paragraphs: 3 }, sources: ['src1'] },
    },
  ],
}

const mockOperationDetail = {
  operation: {
    operation_id: 'op1',
    mode: 'source',
    status: 'completed',
    summary: { counts: { paragraphs: 3 }, sources: ['src1'] },
    items: [],
  },
}

const mockPreview = {
  mode: 'source',
  selector: { sources: ['src1'] },
  counts: { paragraphs: 10 },
  sources: ['src1'],
  items: [],
  item_count: 0,
}

const mockExecuteResult = {
  mode: 'source',
  operation_id: 'op1',
  counts: { paragraphs: 10 },
  sources: ['src1'],
  deleted_count: 10,
  deleted_entity_count: 0,
  deleted_relation_count: 0,
  deleted_paragraph_count: 10,
  deleted_source_count: 1,
  error: undefined,
}

describe('R4-2-7 useMemoryDelete', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getMemorySources).mockResolvedValue(mockSources)
    vi.mocked(getMemoryDeleteOperations).mockResolvedValue(mockOperations)
    vi.mocked(getMemoryDeleteOperation).mockResolvedValue(mockOperationDetail)
    vi.mocked(previewMemoryDelete).mockResolvedValue(mockPreview)
    vi.mocked(executeMemoryDelete).mockResolvedValue(mockExecuteResult)
    vi.mocked(restoreMemoryDelete).mockResolvedValue({})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('active: true 时拉取来源 + 操作列表', async () => {
    const { result } = renderHook(() => useMemoryDelete({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.filteredSources).toHaveLength(2)
    })
    expect(getMemorySources).toHaveBeenCalled()
    expect(getMemoryDeleteOperations).toHaveBeenCalled()
  })

  it('active: false 时不拉取', () => {
    renderHook(() => useMemoryDelete({ active: false }), { wrapper: makeWrapper() })
    expect(getMemorySources).not.toHaveBeenCalled()
    expect(getMemoryDeleteOperations).not.toHaveBeenCalled()
  })

  it('读失败时 deleteErrorText 局部呈现', async () => {
    vi.mocked(getMemorySources).mockRejectedValue(new Error('加载删除数据失败'))
    const { result } = renderHook(() => useMemoryDelete({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.deleteErrorText).toBe('加载删除数据失败')
    })
  })

  it('删除预览-执行成功 → toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryDelete({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.filteredSources).toHaveLength(2)
    })
    // 选中来源
    act(() => {
      result.current.setSelectedSources(['src1'])
    })
    // 打开预览
    await act(async () => {
      await result.current.openSourceDeletePreview()
    })
    expect(result.current.deleteDialogOpen).toBe(true)
    expect(previewMemoryDelete).toHaveBeenCalled()
    // 执行删除
    await act(async () => {
      await result.current.executePendingDelete()
    })
    expect(executeMemoryDelete).toHaveBeenCalled()
    expect(toastSpy).toHaveBeenCalledWith('操作 op1 已完成')
  })

  it('未选来源时预览 → toast.error', async () => {
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryDelete({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.filteredSources).toHaveLength(2)
    })
    await act(async () => {
      await result.current.openSourceDeletePreview()
    })
    expect(toastSpy).toHaveBeenCalledWith('至少选择一个来源后再进行删除预览')
  })

  it('恢复成功 → toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryDelete({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.filteredSources).toHaveLength(2)
    })
    await act(async () => {
      await result.current.restoreDeleteOperation('op1')
    })
    expect(restoreMemoryDelete).toHaveBeenCalledWith({ operation_id: 'op1', requested_by: 'knowledge_base' })
    expect(toastSpy).toHaveBeenCalledWith('删除操作 op1 已恢复')
  })

  it('恢复失败 → toast.error', async () => {
    vi.mocked(restoreMemoryDelete).mockRejectedValue(new Error('恢复失败'))
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryDelete({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.filteredSources).toHaveLength(2)
    })
    await act(async () => {
      await result.current.restoreDeleteOperation('op1')
    })
    expect(toastSpy).toHaveBeenCalledWith('恢复失败')
  })
})