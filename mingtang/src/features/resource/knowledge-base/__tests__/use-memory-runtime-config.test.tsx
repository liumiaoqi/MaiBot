/**
 * useMemoryRuntimeConfig hook 测试（R4-2-4 测试先行）
 *
 * 核心验证：
 * - runtimeConfig 默认即拉取（enabled: true——非懒加载）
 * - 自检刷新：refreshSelfCheck → refreshMemoryRuntimeSelfCheck + 重拉 + toast
 * - 向量重建预览-执行：openVectorRebuildDialog → dry-run → confirm → 真执行
 * - 读失败局部呈现（runtimeErrorText）
 * - 写失败 toast.error
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

vi.mock('@/lib/memory-api', () => ({
  getMemoryRuntimeConfig: vi.fn(),
  refreshMemoryRuntimeSelfCheck: vi.fn(),
  rebuildMemoryRuntimeVectors: vi.fn(),
}))

import {
  getMemoryRuntimeConfig,
  rebuildMemoryRuntimeVectors,
  refreshMemoryRuntimeSelfCheck,
} from '@/lib/memory-api'
import { useMemoryRuntimeConfig } from '../hooks/useMemoryRuntimeConfig'

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

const mockRuntimeConfig = {
  config: {},
  runtime_ready: true,
  embedding_degraded: false,
  embedding_degraded_reason: '',
  embedding_dimension: 1024,
  relation_vectors_enabled: true,
  data_dir: '/data/memory',
  auto_save: false,
  paragraph_vector_backfill_pending: 0,
  paragraph_vector_backfill_running: 0,
  paragraph_vector_backfill_failed: 0,
  paragraph_vector_backfill_done: 0,
}

describe('R4-2-4 useMemoryRuntimeConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getMemoryRuntimeConfig).mockResolvedValue(mockRuntimeConfig)
    vi.mocked(refreshMemoryRuntimeSelfCheck).mockResolvedValue({ error: undefined })
    vi.mocked(rebuildMemoryRuntimeVectors).mockResolvedValue({
      error: undefined,
      done: 10,
      failed: 0,
      counts: { entities: 5, relations: 5 },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('runtimeConfig 默认即拉取（enabled: true——非懒加载）', async () => {
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    expect(result.current.runtimeConfig).toEqual(mockRuntimeConfig)
    expect(getMemoryRuntimeConfig).toHaveBeenCalled()
  })

  it('runtimeLoading 初始为 true，加载完成后为 false', async () => {
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    expect(result.current.runtimeLoading).toBe(true)
    await waitFor(() => {
      expect(result.current.runtimeLoading).toBe(false)
    })
  })

  it('读失败时 runtimeErrorText 局部呈现', async () => {
    vi.mocked(getMemoryRuntimeConfig).mockRejectedValue(new Error('加载失败'))
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeErrorText).toBe('加载失败')
    })
    expect(result.current.runtimeConfig).toBeNull()
  })

  it('自检刷新成功 → toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    await act(async () => {
      await result.current.refreshSelfCheck()
    })
    expect(refreshMemoryRuntimeSelfCheck).toHaveBeenCalled()
    expect(getMemoryRuntimeConfig).toHaveBeenCalledTimes(2)
    expect(toastSpy).toHaveBeenCalledWith('运行时状态正常')
  })

  it('自检刷新失败 → toast.error', async () => {
    vi.mocked(refreshMemoryRuntimeSelfCheck).mockResolvedValue({ error: 'degraded' })
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    await act(async () => {
      await result.current.refreshSelfCheck()
    })
    expect(toastSpy).toHaveBeenCalledWith('请检查 embedding 配置和外部服务连通性')
  })

  it('自检刷新异常 → toast.error', async () => {
    vi.mocked(refreshMemoryRuntimeSelfCheck).mockRejectedValue(new Error('网络错误'))
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    await act(async () => {
      await result.current.refreshSelfCheck()
    })
    expect(toastSpy).toHaveBeenCalledWith('网络错误')
  })

  it('向量重建：openVectorRebuildDialog → dry-run 预览', async () => {
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    await act(async () => {
      await result.current.openVectorRebuildDialog()
    })
    expect(rebuildMemoryRuntimeVectors).toHaveBeenCalledWith({ dry_run: true })
    expect(result.current.vectorRebuildDialogOpen).toBe(true)
    expect(result.current.vectorRebuildPreview).toEqual({ entities: 5, relations: 5 })
  })

  it('向量重建：confirm → 真执行 + toast.success', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    await act(async () => {
      await result.current.openVectorRebuildDialog()
    })
    await act(async () => {
      await result.current.confirmVectorRebuild()
    })
    expect(rebuildMemoryRuntimeVectors).toHaveBeenCalledWith({ dry_run: false })
    expect(toastSpy).toHaveBeenCalledWith('已处理 10 条，失败 0 条')
  })

  it('向量重建：setVectorRebuildDialogOpen(false) → 取消待定', async () => {
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    await act(async () => {
      await result.current.openVectorRebuildDialog()
    })
    expect(result.current.vectorRebuildDialogOpen).toBe(true)
    act(() => {
      result.current.setVectorRebuildDialogOpen(false)
    })
    expect(result.current.vectorRebuildDialogOpen).toBe(false)
    expect(result.current.vectorRebuildPreview).toBeNull()
  })

  it('refreshRuntimeConfig 重拉配置', async () => {
    const { result } = renderHook(() => useMemoryRuntimeConfig(), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.runtimeConfig).not.toBeNull()
    })
    const initialCallCount = vi.mocked(getMemoryRuntimeConfig).mock.calls.length
    await act(async () => {
      await result.current.refreshRuntimeConfig()
    })
    expect(vi.mocked(getMemoryRuntimeConfig).mock.calls.length).toBeGreaterThan(initialCallCount)
  })
})