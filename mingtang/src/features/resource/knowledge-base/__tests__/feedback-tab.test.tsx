/**
 * FeedbackTab 组件测试（R4-2-13）
 *
 * 核心验证：
 * - 渲染基本结构（反馈纠错历史卡片）
 * - 核心交互（选中纠错 + 点击"回退本次纠错" → openFeedbackRollbackDialog）
 * - 加载态（selectedFeedbackTaskLoading: true → 加载区呈现）
 * - 错误态（selectedFeedbackTaskError 非空 → Alert 局部呈现）
 * - 空态（filteredFeedbackCorrections 为空 → 空态文案）
 *
 * 模式：props 注入 mock hook 结果（R4-1 教训 #6/#7）
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Tabs } from '@/components/ui/tabs'

import type { MemoryFeedbackCorrectionDetailTaskPayload, MemoryFeedbackCorrectionSummaryPayload } from '@/lib/memory-api'

import type { UseMemoryFeedbackResult } from '../hooks/useMemoryFeedback'
import { FeedbackTab } from '../tabs/FeedbackTab'

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

function renderFeedbackTab(feedback: UseMemoryFeedbackResult) {
  return render(
    <Tabs value="feedback">
      <FeedbackTab feedback={feedback} />
    </Tabs>,
    { wrapper: makeWrapper() },
  )
}

const mockCorrectionSummary: MemoryFeedbackCorrectionSummaryPayload = {
  task_id: 1,
  query_tool_id: 'tool-1',
  session_id: 'session-1',
  query_text: '查询内容',
  task_status: 'applied',
  decision: 'accepted',
  decision_confidence: 0.9,
  feedback_message_count: 2,
  rollback_status: 'none',
  affected_counts: {},
}

const mockCorrectionDetail: MemoryFeedbackCorrectionDetailTaskPayload = {
  ...mockCorrectionSummary,
  rollback_error: '',
}

function makeMockFeedback(overrides: Partial<UseMemoryFeedbackResult> = {}): UseMemoryFeedbackResult {
  return {
    feedbackSearch: '',
    setFeedbackSearch: vi.fn(),
    feedbackStatusFilter: 'all',
    setFeedbackStatusFilter: vi.fn(),
    feedbackRollbackFilter: 'all',
    setFeedbackRollbackFilter: vi.fn(),
    filteredFeedbackCorrections: [],
    feedbackCorrections: [],
    pagedFeedbackCorrections: [],
    feedbackPage: 1,
    setFeedbackPage: vi.fn(),
    feedbackPageCount: 1,
    selectedFeedbackCorrection: null,
    setSelectedFeedbackTaskId: vi.fn(),
    selectedFeedbackResolved: null,
    selectedFeedbackPreview: { headline: '', oldRelation: '', newRelation: '' },
    selectedFeedbackImpactSummary: [],
    openFeedbackRollbackDialog: vi.fn(),
    feedbackRollingBack: false,
    selectedFeedbackTaskLoading: false,
    selectedFeedbackTaskError: null,
    feedbackActionLogPage: 1,
    setFeedbackActionLogPage: vi.fn(),
    feedbackActionLogPageCount: 1,
    feedbackActionLogSearch: '',
    setFeedbackActionLogSearch: vi.fn(),
    pagedFeedbackActionLogs: [],
    selectedFeedbackActionLogs: [],
    feedbackRollbackDialogOpen: false,
    setFeedbackRollbackDialogOpen: vi.fn(),
    feedbackRollbackReason: '',
    setFeedbackRollbackReason: vi.fn(),
    executeFeedbackRollback: vi.fn(),
    feedbackErrorText: '',
    ...overrides,
  }
}

describe('R4-2-13 FeedbackTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染基本结构：反馈纠错历史卡片', () => {
    renderFeedbackTab(makeMockFeedback())
    expect(screen.getByText('反馈纠错历史')).toBeInTheDocument()
  })

  it('核心交互：选中纠错 + 点击"回退本次纠错" → openFeedbackRollbackDialog 调用', () => {
    const feedback = makeMockFeedback({
      selectedFeedbackCorrection: mockCorrectionSummary,
      selectedFeedbackResolved: mockCorrectionDetail,
      selectedFeedbackPreview: { headline: '纠错标题', oldRelation: '旧关系', newRelation: '新关系' },
    })
    renderFeedbackTab(feedback)
    const button = screen.getByRole('button', { name: /回退本次纠错/ })
    fireEvent.click(button)
    expect(feedback.openFeedbackRollbackDialog).toHaveBeenCalledTimes(1)
  })

  it('加载态：selectedFeedbackTaskLoading + 选中纠错 → 加载区呈现', () => {
    const feedback = makeMockFeedback({
      selectedFeedbackCorrection: mockCorrectionSummary,
      selectedFeedbackResolved: mockCorrectionDetail,
      selectedFeedbackPreview: { headline: '纠错标题', oldRelation: '', newRelation: '' },
      selectedFeedbackTaskLoading: true,
    })
    renderFeedbackTab(feedback)
    expect(screen.getAllByRole('status', { name: '加载中' }).length).toBeGreaterThan(0)
  })

  it('错误态：selectedFeedbackTaskError 非空 → Alert 局部呈现', () => {
    const feedback = makeMockFeedback({
      selectedFeedbackCorrection: mockCorrectionSummary,
      selectedFeedbackResolved: mockCorrectionDetail,
      selectedFeedbackPreview: { headline: '纠错标题', oldRelation: '', newRelation: '' },
      selectedFeedbackTaskError: '加载纠错详情失败',
    })
    renderFeedbackTab(feedback)
    expect(screen.getByText('加载纠错详情失败')).toBeInTheDocument()
  })

  it('空态：filteredFeedbackCorrections 为空 → 空态文案呈现', () => {
    renderFeedbackTab(makeMockFeedback())
    expect(screen.getByText('当前筛选条件下没有纠错历史')).toBeInTheDocument()
  })
})