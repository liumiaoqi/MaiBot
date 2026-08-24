/**
 * StageStatusPanel 子组件测试
 *
 * 核心验证：
 * - 阶段信息展示（阶段名/轮次/智能体状态/详情）
 * - 无状态时占位文案
 * - 操作按钮（清空/回到底部/持续获取开关）
 * - 统计 tooltip trigger 渲染
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'time' in opts) return `${key}:${opts.time}`
      if (opts && typeof opts === 'object' && 'count' in opts) return `${key}(${opts.count})`
      return key
    },
  }),
}))

vi.mock('../components/timeline-entry-item', () => ({
  TimelineEntryItem: () => null,
  formatRelativeTime: () => ({ key: 'monitor.maisaka.justNow' }),
  formatMs: () => '0ms',
  formatTimestamp: () => '00:00:00',
}))

import { StageStatusPanel } from '../components/stage-status-panel'
import type { StageStatusInfo, MonitorStats } from '../hooks/persist-monitor'

function makeStatus(overrides: Partial<StageStatusInfo> = {}): StageStatusInfo {
  return {
    sessionId: 'sess-1',
    stage: '思考中',
    detail: '正在推理',
    roundText: '第1轮',
    agentState: 'running',
    stageStartedAt: 1000,
    updatedAt: 1000,
    ...overrides,
  }
}

function makeStats(overrides: Partial<MonitorStats> = {}): MonitorStats {
  return { messages: 0, cycles: 0, toolCalls: 0, ...overrides }
}

function renderPanel(overrides: { status?: StageStatusInfo; onClearTimeline?: () => void; onToggleBackgroundCollection?: () => void; onScrollToBottom?: () => void } = {}) {
  const onClearTimeline = overrides.onClearTimeline ?? vi.fn()
  const onToggleBackgroundCollection = overrides.onToggleBackgroundCollection ?? vi.fn()
  const onScrollToBottom = overrides.onScrollToBottom ?? vi.fn()
  render(
    <StageStatusPanel
      status={overrides.status}
      stats={makeStats()}
      autoScroll={true}
      backgroundCollection={false}
      onClearTimeline={onClearTimeline}
      onToggleBackgroundCollection={onToggleBackgroundCollection}
      onScrollToBottom={onScrollToBottom}
    />,
  )
  return { onClearTimeline, onToggleBackgroundCollection, onScrollToBottom }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('StageStatusPanel', () => {
  it('展示阶段信息（阶段名/轮次/智能体状态/详情）', () => {
    renderPanel({ status: makeStatus() })
    expect(screen.getByText('思考中')).toBeInTheDocument()
    expect(screen.getByText('第1轮')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('正在推理')).toBeInTheDocument()
  })

  it('无状态时显示占位文案', () => {
    renderPanel({ status: undefined })
    expect(screen.getByText('monitor.maisaka.noStageStatus')).toBeInTheDocument()
  })

  it('清空按钮调用 onClearTimeline', () => {
    const onClearTimeline = vi.fn()
    renderPanel({ onClearTimeline })
    fireEvent.click(screen.getByLabelText('monitor.maisaka.clear'))
    expect(onClearTimeline).toHaveBeenCalledOnce()
  })

  it('持续获取按钮调用 onToggleBackgroundCollection', () => {
    const onToggle = vi.fn()
    renderPanel({ onToggleBackgroundCollection: onToggle })
    fireEvent.click(screen.getByText('monitor.maisaka.backgroundCollection'))
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('回到底部按钮调用 onScrollToBottom', () => {
    const onScroll = vi.fn()
    renderPanel({ onScrollToBottom: onScroll })
    fireEvent.click(screen.getByText('monitor.maisaka.scrollToBottom'))
    expect(onScroll).toHaveBeenCalledOnce()
  })

  it('统计信息 trigger 渲染', () => {
    renderPanel({ status: makeStatus() })
    expect(screen.getByText('monitor.maisaka.stats')).toBeInTheDocument()
  })

  it('stage 为空时显示未知阶段占位', () => {
    renderPanel({ status: makeStatus({ stage: '' }) })
    expect(screen.getByText('monitor.maisaka.unknownStage')).toBeInTheDocument()
  })
})