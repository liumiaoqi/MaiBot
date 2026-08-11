/**
 * useImportQueue hook 测试（R4-2-6）
 *
 * 核心验证：
 * - 任务列表仅在 active 时拉取（enabled: active 门控）
 * - WS 连接状态控制轮询兜底
 * - 取消任务 → cancelMemoryImportTask + toast.success
 * - 重试任务 → retryMemoryImportTask + toast.success
 * - 读失败局部呈现（importErrorText）
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

vi.mock('@/lib/memory-api', () => ({
  getMemoryImportSettings: vi.fn(),
  getMemoryImportTasks: vi.fn(),
  getMemoryImportTask: vi.fn(),
  getMemoryImportTaskChunks: vi.fn(),
  cancelMemoryImportTask: vi.fn(),
  retryMemoryImportTask: vi.fn(),
}))

vi.mock('@/lib/memory-progress-client', () => ({
  memoryProgressClient: {
    subscribe: vi.fn().mockResolvedValue(async () => {}),
  },
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: {
    onConnectionChange: vi.fn(() => () => {}),
    addEventListener: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
  },
}))

import {
  cancelMemoryImportTask,
  getMemoryImportSettings,
  getMemoryImportTask,
  getMemoryImportTaskChunks,
  getMemoryImportTasks,
  retryMemoryImportTask,
} from '@/lib/memory-api'
import { useImportQueue } from '../hooks/useImportQueue'

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

const mockSettings = { settings: { poll_interval_ms: 1000 } }

const mockTask = {
  task_id: 'task-1',
  source: 'upload',
  status: 'completed',
  current_step: 'completed',
  total_chunks: 10,
  done_chunks: 10,
  failed_chunks: 0,
  cancelled_chunks: 0,
  progress: 100,
  error: '',
  file_count: 1,
  created_at: 1700000000,
  updated_at: 1700000000,
  files: [],
}

const mockTasks = { items: [mockTask], count: 1 }

const mockTaskDetail = { task: mockTask }

const mockChunks = { items: [], total: 0 }

describe('R4-2-6 useImportQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getMemoryImportSettings).mockResolvedValue(mockSettings)
    vi.mocked(getMemoryImportTasks).mockResolvedValue(mockTasks)
    vi.mocked(getMemoryImportTask).mockResolvedValue(mockTaskDetail)
    vi.mocked(getMemoryImportTaskChunks).mockResolvedValue(mockChunks)
    vi.mocked(cancelMemoryImportTask).mockResolvedValue({ task: mockTask })
    vi.mocked(retryMemoryImportTask).mockResolvedValue({ task: { ...mockTask, task_id: 'task-2' } })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('active: true 时拉取任务列表', async () => {
    const { result } = renderHook(() => useImportQueue({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.recentImportTasks).toHaveLength(1)
    })
    expect(getMemoryImportTasks).toHaveBeenCalled()
  })

  it('active: false 时不拉取', () => {
    renderHook(() => useImportQueue({ active: false }), { wrapper: makeWrapper() })
    expect(getMemoryImportTasks).not.toHaveBeenCalled()
  })

  it('读失败时 importErrorText 局部呈现', async () => {
    vi.mocked(getMemoryImportTasks).mockRejectedValue(new Error('刷新导入任务失败'))
    const { result } = renderHook(() => useImportQueue({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importErrorText).toBe('刷新导入任务失败')
    })
  })

  it('取消任务成功 → toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const { result } = renderHook(() => useImportQueue({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.recentImportTasks).toHaveLength(1)
    })
    // 等待自动选中第一个任务
    await waitFor(() => {
      expect(result.current.selectedImportTaskId).toBe('task-1')
    })
    await act(async () => {
      await result.current.cancelSelectedImportTask()
    })
    expect(cancelMemoryImportTask).toHaveBeenCalledWith('task-1')
    expect(toastSpy).toHaveBeenCalledWith('任务 task-1 正在取消')
  })

  it('取消任务失败 → toast.error', async () => {
    vi.mocked(cancelMemoryImportTask).mockRejectedValue(new Error('取消失败'))
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useImportQueue({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.recentImportTasks).toHaveLength(1)
    })
    await waitFor(() => {
      expect(result.current.selectedImportTaskId).toBe('task-1')
    })
    await act(async () => {
      await result.current.cancelSelectedImportTask()
    })
    expect(toastSpy).toHaveBeenCalledWith('取消失败')
  })

  it('重试任务成功 → toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const buildRetryOverrides = vi.fn(() => ({})
    )
    const { result } = renderHook(
      () => useImportQueue({ active: true, buildRetryOverrides }),
      { wrapper: makeWrapper() },
    )
    await waitFor(() => {
      expect(result.current.recentImportTasks).toHaveLength(1)
    })
    await waitFor(() => {
      expect(result.current.selectedImportTaskId).toBe('task-1')
    })
    await act(async () => {
      await result.current.retrySelectedImportTask()
    })
    expect(retryMemoryImportTask).toHaveBeenCalledWith('task-1', { overrides: {} })
    expect(toastSpy).toHaveBeenCalledWith('重试任务 task-2 已进入队列')
  })
})