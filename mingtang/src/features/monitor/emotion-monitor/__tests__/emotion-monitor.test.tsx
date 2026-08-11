/**
 * EmotionMonitorPage 测试（T1-3-3 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 情绪雷达图/柱状图渲染（grid 卡片 + detail 详情）
 * - agent 选择：点击卡片进入 detail，返回按钮回 grid
 * - 页面标题 + agentCount badge
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: { select: (s: { location: { search: Record<string, unknown> } }) => unknown }) =>
    select({ location: { search: {} } }),
}))

const { mockGetAgentList, mockGetAgentEmotion } = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetAgentEmotion: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getAgentEmotion: mockGetAgentEmotion,
}))

import { EmotionMonitorPage } from '../index'
import type { AgentConfigInfo, EmotionStateInfo } from '@/lib/agent-api'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeAgent(id: string, name: string): AgentConfigInfo {
  return {
    agent_id: id,
    display_name: name,
    personality: '温柔',
    reply_style: '活泼',
    is_default: false,
    color: '#55AB49',
    emotion_baseline: { happy: 0.5, calm: 0.4 },
    emotion_decay_rate: 0.9,
    relationship_growth_rate: 0.1,
    talk_value_modifier: 1.0,
    memory_focus_areas: ['chat'],
    internal_relationships: [],
    anti_mechanization_rules: [],
  }
}

function makeEmotion(agentId: string, dominant: string): EmotionStateInfo {
  return {
    agent_id: agentId,
    emotions: { happy: 60, calm: 40 },
    dominant_emotion: dominant,
    dominant_emotion_label: dominant === 'happy' ? '开心' : '平静',
    emotion_labels: { happy: '开心', calm: '平静' },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetAgentList.mockResolvedValue([makeAgent('agent-a', '麦麦'), makeAgent('agent-b', '小助手')])
  mockGetAgentEmotion.mockImplementation((agentId: string) =>
    Promise.resolve(makeEmotion(agentId, agentId === 'agent-a' ? 'happy' : 'calm'))
  )
})

describe('EmotionMonitorPage', () => {
  it('PageShell 渲染 + 标题', async () => {
    render(<EmotionMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.emotion.title')).toBeInTheDocument()
  })

  it('agentCount badge 渲染', async () => {
    render(<EmotionMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('emotion.agentCount')).toBeInTheDocument()
    })
  })

  it('grid 视图渲染 agent 卡片（display_name + 主导情绪）', async () => {
    render(<EmotionMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    expect(screen.getByText('小助手')).toBeInTheDocument()
    expect(screen.getAllByText((c) => c.includes('开心')).length).toBeGreaterThan(0)
  })

  it('点击卡片进入 detail（雷达图 + 基线对比 + 行为参数）', async () => {
    const user = userEvent.setup()
    render(<EmotionMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('麦麦'))

    await waitFor(() => {
      expect(screen.getByText('monitor.emotion.radar')).toBeInTheDocument()
    })
    expect(screen.getByText('monitor.emotion.baseline')).toBeInTheDocument()
    expect(screen.getByText('emotion.behaviorParams')).toBeInTheDocument()
    expect(screen.getByText('emotion.intensityTitle')).toBeInTheDocument()
  })

  it('detail 视图返回按钮回 grid', async () => {
    const user = userEvent.setup()
    render(<EmotionMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('麦麦'))
    await waitFor(() => {
      expect(screen.getByText('monitor.emotion.radar')).toBeInTheDocument()
    })

    await user.click(screen.getByText('emotion.backToOverview'))
    await waitFor(() => {
      expect(screen.queryByText('monitor.emotion.radar')).not.toBeInTheDocument()
    })
    expect(screen.getByText('麦麦')).toBeInTheDocument()
  })
})