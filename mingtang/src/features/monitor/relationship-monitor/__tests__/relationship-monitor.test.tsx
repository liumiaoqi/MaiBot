/**
 * RelationshipMonitorPage 测试（T1-4-3 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 关系等级分布/排行渲染 + agent 选择（左列表 → 右详情）
 * - 空态：未选中智能体提示 + 无关系数据提示
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

const { mockGetAgentList, mockGetAgentRelationships } = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetAgentRelationships: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getAgentRelationships: mockGetAgentRelationships,
}))

import { RelationshipMonitorPage } from '../index'
import type { AgentConfigInfo, RelationshipInfo } from '@/lib/agent-api'

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

function makeRelationship(userId: string, level: number, score: number): RelationshipInfo {
  const levelName = ['陌生人', '认识', '熟悉', '亲密'][level] ?? '陌生人'
  return {
    user_id: userId,
    level,
    level_name: levelName,
    score,
    total_interactions: 10,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetAgentList.mockResolvedValue([makeAgent('agent-a', '麦麦'), makeAgent('agent-b', '小助手')])
  mockGetAgentRelationships.mockImplementation((agentId: string) =>
    Promise.resolve(
      agentId === 'agent-a'
        ? [makeRelationship('user-1', 3, 980), makeRelationship('user-2', 2, 700)]
        : [makeRelationship('user-3', 1, 500)]
    )
  )
})

describe('RelationshipMonitorPage', () => {
  it('PageShell 渲染 + 标题', async () => {
    render(<RelationshipMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.relationship.title')).toBeInTheDocument()
  })

  it('agent 卡片列表渲染 + 关系数 badge', async () => {
    render(<RelationshipMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    expect(screen.getByText('小助手')).toBeInTheDocument()
    expect(screen.getByText((c) => c.includes('2 智能体') && c.includes('3 条关系'))).toBeInTheDocument()
  })

  it('未选中时显示空态提示', async () => {
    render(<RelationshipMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByText('选择一个智能体查看关系详情')).toBeInTheDocument()
  })

  it('点击 agent 卡片进入详情（等级分布 + 平均分数 + 排行）', async () => {
    const user = userEvent.setup()
    render(<RelationshipMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('麦麦'))

    await waitFor(() => {
      expect(screen.getByText('monitor.relationship.distribution')).toBeInTheDocument()
    })
    expect(screen.getByText('平均分数')).toBeInTheDocument()
    expect(screen.getByText('monitor.relationship.ranking')).toBeInTheDocument()
    expect(screen.getByText('关系进展速率 ×0.1 · 2 条关系')).toBeInTheDocument()
  })

  it('详情显示等级统计卡片（0-3 级）', async () => {
    const user = userEvent.setup()
    render(<RelationshipMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('麦麦'))

    await waitFor(() => {
      expect(screen.getByText('monitor.relationship.distribution')).toBeInTheDocument()
    })
    expect(screen.getAllByText('陌生人').length).toBeGreaterThan(0)
    expect(screen.getAllByText('认识').length).toBeGreaterThan(0)
    expect(screen.getAllByText('熟悉').length).toBeGreaterThan(0)
    expect(screen.getAllByText('亲密').length).toBeGreaterThan(0)
  })

  it('关系为空时显示暂无数据提示', async () => {
    mockGetAgentRelationships.mockResolvedValue([])
    const user = userEvent.setup()
    render(<RelationshipMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('麦麦'))

    await waitFor(() => {
      expect(screen.getByText('暂无关系数据')).toBeInTheDocument()
    })
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })
})