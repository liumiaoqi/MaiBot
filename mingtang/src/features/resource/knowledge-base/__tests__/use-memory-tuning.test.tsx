/**
 * useMemoryTuning hook 测试（R4-2-9）
 *
 * 核心验证：
 * - 调优配置/任务列表仅在 active 时拉取（enabled: active 门控）
 * - 创建调优任务 → createMemoryTuningTask + 刷新列表 + toast.success
 * - 应用最佳参数 → applyBestMemoryTuningProfile + 刷新 + onRuntimeChanged + toast.success
 * - 读失败局部呈现（tuningErrorText）
 * - 写失败 toast.error
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

vi.mock('@/lib/memory-api', () => ({
  getMemoryTuningProfile: vi.fn(),
  getMemoryTuningTasks: vi.fn(),
  createMemoryTuningTask: vi.fn(),
  applyBestMemoryTuningProfile: vi.fn(),
}))

import {
  applyBestMemoryTuningProfile,
  createMemoryTuningTask,
  getMemoryTuningProfile,
  getMemoryTuningTasks,
} from '@/lib/memory-api'
import { useMemoryTuning } from '../hooks/useMemoryTuning'

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

const mockProfile = {
  profile: { top_k: 20 },
  runtime_profile: { top_k: 20 },
  persistable_profile: { top_k: 20 },
  toml: 'top_k = 20',
}

const mockTasks = {
  items: [
    { task_id: 't1', status: 'completed', mode: 'precision_priority' },
  ],
  count: 1,
}

describe('R4-2-9 useMemoryTuning', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getMemoryTuningProfile).mockResolvedValue(mockProfile)
    vi.mocked(getMemoryTuningTasks).mockResolvedValue(mockTasks)
    vi.mocked(createMemoryTuningTask).mockResolvedValue({ task: { task_id: 't2' } })
    vi.mocked(applyBestMemoryTuningProfile).mockResolvedValue({
      error: undefined,
      persisted: true,
      runtime_rebuilt: true,
      validation_passed: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('active: true 时拉取 profile + tasks', async () => {
    const { result } = renderHook(() => useMemoryTuning({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.tuningTasks).toHaveLength(1)
    })
    expect(result.current.tuningProfileToml).toBe('top_k = 20')
    expect(getMemoryTuningProfile).toHaveBeenCalled()
    expect(getMemoryTuningTasks).toHaveBeenCalled()
  })

  it('active: false 时不拉取', () => {
    renderHook(() => useMemoryTuning({ active: false }), { wrapper: makeWrapper() })
    expect(getMemoryTuningProfile).not.toHaveBeenCalled()
    expect(getMemoryTuningTasks).not.toHaveBeenCalled()
  })

  it('读失败时 tuningErrorText 局部呈现', async () => {
    vi.mocked(getMemoryTuningProfile).mockRejectedValue(new Error('加载调优数据失败'))
    const { result } = renderHook(() => useMemoryTuning({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.tuningErrorText).toBe('加载调优数据失败')
    })
  })

  it('submitTuningTask 成功 → toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryTuning({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.tuningTasks).toHaveLength(1)
    })
    await act(async () => {
      await result.current.submitTuningTask()
    })
    expect(createMemoryTuningTask).toHaveBeenCalled()
    expect(toastSpy).toHaveBeenCalledWith('新的检索调优任务已经进入队列')
  })

  it('submitTuningTask 失败 → toast.error', async () => {
    vi.mocked(createMemoryTuningTask).mockRejectedValue(new Error('创建失败'))
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryTuning({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.tuningTasks).toHaveLength(1)
    })
    await act(async () => {
      await result.current.submitTuningTask()
    })
    expect(toastSpy).toHaveBeenCalledWith('创建失败')
  })

  it('applyBestTask 成功 → toast.success + onRuntimeChanged', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const onRuntimeChanged = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(
      () => useMemoryTuning({ active: true, onRuntimeChanged }),
      { wrapper: makeWrapper() },
    )
    await waitFor(() => {
      expect(result.current.tuningTasks).toHaveLength(1)
    })
    await act(async () => {
      await result.current.applyBestTask('t1')
    })
    expect(applyBestMemoryTuningProfile).toHaveBeenCalledWith('t1', { persist: false, validate: true })
    expect(onRuntimeChanged).toHaveBeenCalled()
    expect(toastSpy).toHaveBeenCalledWith('任务 t1 的最佳轮次已经写入运行时和配置文件')
  })

  it('applyBestTask 失败 → toast.error', async () => {
    vi.mocked(applyBestMemoryTuningProfile).mockRejectedValue(new Error('应用失败'))
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryTuning({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.tuningTasks).toHaveLength(1)
    })
    await act(async () => {
      await result.current.applyBestTask('t1')
    })
    expect(toastSpy).toHaveBeenCalledWith('应用失败')
  })
})