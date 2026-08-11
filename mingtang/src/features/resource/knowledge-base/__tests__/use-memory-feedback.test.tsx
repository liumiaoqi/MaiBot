/**
 * useMemoryFeedback hook 测试（R4-2-8）
 *
 * 核心验证：
 * - 纠错历史列表仅在 active 时拉取（enabled: active 门控）
 * - 回退成功 → rollbackMemoryFeedbackCorrection + 刷新 + onRuntimeChanged/onSourcesChanged + toast.success
 * - 读失败局部呈现（feedbackErrorText）
 * - 写失败 toast.error
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

vi.mock('@/lib/memory-api', () => ({
  getMemoryFeedbackCorrections: vi.fn(),
  getMemoryFeedbackCorrection: vi.fn(),
  rollbackMemoryFeedbackCorrection: vi.fn(),
}))

vi.mock('../utils', () => ({
  buildFeedbackImpactSummary: vi.fn(() => []),
  getFeedbackCorrectionPreview: vi.fn(() => ({ before: null, after: null })),
  summarizeFeedbackActionPayload: vi.fn(() => ''),
}))

import {
  getMemoryFeedbackCorrection,
  getMemoryFeedbackCorrections,
  rollbackMemoryFeedbackCorrection,
} from '@/lib/memory-api'
import { useMemoryFeedback } from '../hooks/useMemoryFeedback'

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

const mockCorrections = {
  items: [
    {
      task_id: 1,
      query_tool_id: 'tool-1',
      session_id: 's1',
      query_text: '测试查询',
      task_status: 'completed',
      decision: 'accept',
      decision_confidence: 0.9,
      feedback_message_count: 2,
      rollback_status: '',
      affected_counts: {},
    },
  ],
}

const mockCorrectionDetail = {
  task: {
    task_id: 1,
    query_tool_id: 'tool-1',
    session_id: 's1',
    query_text: '测试查询',
    task_status: 'completed',
    decision: 'accept',
    decision_confidence: 0.9,
    feedback_message_count: 2,
    rollback_status: '',
    affected_counts: {},
    action_logs: [],
  },
}

describe('R4-2-8 useMemoryFeedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getMemoryFeedbackCorrections).mockResolvedValue(mockCorrections)
    vi.mocked(getMemoryFeedbackCorrection).mockResolvedValue(mockCorrectionDetail)
    vi.mocked(rollbackMemoryFeedbackCorrection).mockResolvedValue({
      error: undefined,
      already_rolled_back: false,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('active: true 时拉取纠错历史列表', async () => {
    const { result } = renderHook(() => useMemoryFeedback({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.feedbackCorrections).toHaveLength(1)
    })
    expect(getMemoryFeedbackCorrections).toHaveBeenCalled()
  })

  it('active: false 时不拉取', () => {
    renderHook(() => useMemoryFeedback({ active: false }), { wrapper: makeWrapper() })
    expect(getMemoryFeedbackCorrections).not.toHaveBeenCalled()
  })

  it('读失败时 feedbackErrorText 局部呈现', async () => {
    vi.mocked(getMemoryFeedbackCorrections).mockRejectedValue(new Error('加载纠错历史失败'))
    const { result } = renderHook(() => useMemoryFeedback({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.feedbackErrorText).toBe('加载纠错历史失败')
    })
  })

  it('回退成功 → toast.success + onRuntimeChanged/onSourcesChanged', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const onRuntimeChanged = vi.fn().mockResolvedValue(undefined)
    const onSourcesChanged = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(
      () => useMemoryFeedback({ active: true, onRuntimeChanged, onSourcesChanged }),
      { wrapper: makeWrapper() },
    )
    await waitFor(() => {
      expect(result.current.feedbackCorrections).toHaveLength(1)
    })
    // 选中纠错任务并打开回退对话框
    act(() => {
      result.current.setSelectedFeedbackTaskId(1)
    })
    await waitFor(() => {
      expect(result.current.selectedFeedbackResolved).not.toBeNull()
    })
    act(() => {
      result.current.openFeedbackRollbackDialog()
    })
    await act(async () => {
      await result.current.executeFeedbackRollback()
    })
    expect(rollbackMemoryFeedbackCorrection).toHaveBeenCalledWith(1, {
      requested_by: 'knowledge_base',
      reason: '',
    })
    expect(onRuntimeChanged).toHaveBeenCalled()
    expect(onSourcesChanged).toHaveBeenCalled()
    expect(toastSpy).toHaveBeenCalledWith('任务 1 的回退结果已写入日志')
  })

  it('回退失败 → toast.error', async () => {
    vi.mocked(rollbackMemoryFeedbackCorrection).mockRejectedValue(new Error('回退失败'))
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryFeedback({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.feedbackCorrections).toHaveLength(1)
    })
    act(() => {
      result.current.setSelectedFeedbackTaskId(1)
    })
    await waitFor(() => {
      expect(result.current.selectedFeedbackResolved).not.toBeNull()
    })
    act(() => {
      result.current.openFeedbackRollbackDialog()
    })
    await act(async () => {
      await result.current.executeFeedbackRollback()
    })
    expect(toastSpy).toHaveBeenCalledWith('回退失败')
  })

  it('回退返回 error → toast.error', async () => {
    vi.mocked(rollbackMemoryFeedbackCorrection).mockResolvedValue({
      error: '权限不足',
      already_rolled_back: false,
    })
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useMemoryFeedback({ active: true }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.feedbackCorrections).toHaveLength(1)
    })
    act(() => {
      result.current.setSelectedFeedbackTaskId(1)
    })
    await waitFor(() => {
      expect(result.current.selectedFeedbackResolved).not.toBeNull()
    })
    act(() => {
      result.current.openFeedbackRollbackDialog()
    })
    await act(async () => {
      await result.current.executeFeedbackRollback()
    })
    expect(toastSpy).toHaveBeenCalledWith('权限不足')
  })
})