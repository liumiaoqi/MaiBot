/**
 * CommandCenterLayout 测试（T2-10-3 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 3 子视图编排（dashboard/constellation/global）——CommandCenterLayout 为调用树根
 * - ViewSwitcher 切换视图
 * - dashboard 视图 VitalSignsCard 渲染（displayName + agentId）
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
  useRouterState: (arg?: { select?: (s: { location: { search: Record<string, unknown> } }) => unknown }) =>
    arg?.select ? arg.select({ location: { search: {} } }) : { location: { search: {} } },
  useNavigate: () => mockNavigate,
}))

vi.mock('@xyflow/react', () => ({
  ReactFlow: () => <div data-testid="reactflow" />,
  Background: () => null,
  BackgroundVariant: { Dots: 'dots' },
  useNodesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
  MarkerType: { ArrowClosed: 'arrowclosed' },
}))

const {
  mockGetAgentList,
  mockGetBatchEmotions,
  mockGetBatchRelationships,
  mockGetBatchSessionCounts,
  mockGetBatchLatestSubAgentRecords,
  mockGetRecentInteractions,
  mockGetInteractionHotspots,
  mockGetInteractionConfig,
  mockManualTriggerInteraction,
  mockNavigate,
} = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetBatchEmotions: vi.fn(),
  mockGetBatchRelationships: vi.fn(),
  mockGetBatchSessionCounts: vi.fn(),
  mockGetBatchLatestSubAgentRecords: vi.fn(),
  mockGetRecentInteractions: vi.fn(),
  mockGetInteractionHotspots: vi.fn(),
  mockGetInteractionConfig: vi.fn(),
  mockManualTriggerInteraction: vi.fn(),
  mockNavigate: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getBatchEmotions: mockGetBatchEmotions,
  getBatchRelationships: mockGetBatchRelationships,
  getBatchSessionCounts: mockGetBatchSessionCounts,
  getBatchLatestSubAgentRecords: mockGetBatchLatestSubAgentRecords,
  getRecentInteractions: mockGetRecentInteractions,
  getInteractionHotspots: mockGetInteractionHotspots,
  getInteractionConfig: mockGetInteractionConfig,
  manualTriggerInteraction: mockManualTriggerInteraction,
}))

import { CommandCenterLayout } from '../components/command-center-layout'
import type { AgentConfigInfo } from '@/lib/agent-api'

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
    emotion_baseline: { happy: 0.5 },
    emotion_decay_rate: 0.9,
    relationship_growth_rate: 0.1,
    talk_value_modifier: 1.0,
    memory_focus_areas: ['chat'],
    internal_relationships: [],
    anti_mechanization_rules: [],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetAgentList.mockResolvedValue([makeAgent('agent-a', '麦麦'), makeAgent('agent-b', '小助手')])
  mockGetBatchEmotions.mockResolvedValue({})
  mockGetBatchRelationships.mockResolvedValue({ data: {}, internal_relationships_summary: {} })
  mockGetBatchSessionCounts.mockResolvedValue({})
  mockGetBatchLatestSubAgentRecords.mockResolvedValue({})
  mockGetRecentInteractions.mockResolvedValue([])
  mockGetInteractionHotspots.mockResolvedValue([])
  mockGetInteractionConfig.mockResolvedValue({
    enabled: true,
    cooldown_minutes: 30,
    max_interactions_per_hour: 5,
    max_interactions_per_day: 20,
    echo_enabled: true,
    echo_max_depth: 2,
  })
  mockManualTriggerInteraction.mockResolvedValue({ event_id: 'e1' })
})

describe('CommandCenterLayout', () => {
  it('dashboard 视图：标题 + 搜索框 + VitalSignsCard（displayName + agentId）', async () => {
    render(<CommandCenterLayout />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('agent.commandCenter.title')).toBeInTheDocument()
    })
    expect(screen.getByPlaceholderText('agent.commandCenter.searchPlaceholder')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    expect(screen.getByText('小助手')).toBeInTheDocument()
    expect(screen.getByText('agent-a')).toBeInTheDocument()
    expect(screen.getByText('agent-b')).toBeInTheDocument()
  })

  it('ViewSwitcher 渲染 3 个视图按钮', async () => {
    render(<CommandCenterLayout />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('agent.commandCenter.dashboard')).toBeInTheDocument()
    })
    expect(screen.getByText('agent.commandCenter.constellation')).toBeInTheDocument()
    expect(screen.getByText('agent.commandCenter.global')).toBeInTheDocument()
  })

  it('切换到 constellation 视图渲染 AgentConstellation', async () => {
    const user = userEvent.setup()
    render(<CommandCenterLayout />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('agent.commandCenter.constellation'))

    await waitFor(() => {
      expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    })
  })

  it('切换到 global 视图渲染 GlobalSituationView + InteractionStream', async () => {
    const user = userEvent.setup()
    render(<CommandCenterLayout />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByText('agent.commandCenter.global'))

    await waitFor(() => {
      expect(screen.getByText('agent.globalSituation.activityHeatmap')).toBeInTheDocument()
    })
    expect(screen.getByText('agent.globalSituation.relationshipDynamics')).toBeInTheDocument()
    expect(mockGetRecentInteractions).toHaveBeenCalled()
    expect(mockGetInteractionHotspots).toHaveBeenCalled()
  })

  it('搜索过滤 VitalSignsCard', async () => {
    const user = userEvent.setup()
    render(<CommandCenterLayout />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.type(screen.getByPlaceholderText('agent.commandCenter.searchPlaceholder'), '麦麦')

    expect(screen.getByText('麦麦')).toBeInTheDocument()
    expect(screen.queryByText('小助手')).not.toBeInTheDocument()
  })
})