/**
 * InnerWorldView 测试（T2-10-2 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 7 tab 编排（emotion/relationship/memory/timeline/sessions/monologue/autonomy）
 * - 各 tab 子组件渲染（EmotionLandscape/RelationshipNetwork/MemoryGarden/LifeTimeline/ActiveSessions/MonologuePanel/AutonomyLogPanel）
 * - Radix Tabs 用 userEvent.click 切换（R3-W-19 教训）
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
  Link: ({ to, search, children }: { to: string; search: { agent: string }; children: ReactNode }) => (
    <a data-to={to} data-search={JSON.stringify(search)}>{children}</a>
  ),
}))

const {
  mockGetAgentList,
  mockGetBatchEmotions,
  mockGetBatchRelationships,
  mockGetBatchSessionCounts,
  mockGetBatchLatestSubAgentRecords,
  mockGetAgentDetail,
  mockGetAgentEmotion,
  mockGetAgentRelationships,
  mockGetSessionsByAgent,
  mockGetSubAgentRecords,
  mockGetEmotionBehaviorRules,
  mockBindSessionAgent,
  mockUnbindSessionAgent,
  mockGetInteractionHotspots,
  mockGetAgentMonologues,
  mockGetAutonomyLogs,
  mockFetchStateAwareness,
  mockGetChatStreams,
  mockGetMigrationStates,
  mockAdvanceMigration,
} = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetBatchEmotions: vi.fn(),
  mockGetBatchRelationships: vi.fn(),
  mockGetBatchSessionCounts: vi.fn(),
  mockGetBatchLatestSubAgentRecords: vi.fn(),
  mockGetAgentDetail: vi.fn(),
  mockGetAgentEmotion: vi.fn(),
  mockGetAgentRelationships: vi.fn(),
  mockGetSessionsByAgent: vi.fn(),
  mockGetSubAgentRecords: vi.fn(),
  mockGetEmotionBehaviorRules: vi.fn(),
  mockBindSessionAgent: vi.fn(),
  mockUnbindSessionAgent: vi.fn(),
  mockGetInteractionHotspots: vi.fn(),
  mockGetAgentMonologues: vi.fn(),
  mockGetAutonomyLogs: vi.fn(),
  mockFetchStateAwareness: vi.fn(),
  mockGetChatStreams: vi.fn(),
  mockGetMigrationStates: vi.fn(),
  mockAdvanceMigration: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getBatchEmotions: mockGetBatchEmotions,
  getBatchRelationships: mockGetBatchRelationships,
  getBatchSessionCounts: mockGetBatchSessionCounts,
  getBatchLatestSubAgentRecords: mockGetBatchLatestSubAgentRecords,
  getAgentDetail: mockGetAgentDetail,
  getAgentEmotion: mockGetAgentEmotion,
  getAgentRelationships: mockGetAgentRelationships,
  getSessionsByAgent: mockGetSessionsByAgent,
  getSubAgentRecords: mockGetSubAgentRecords,
  getEmotionBehaviorRules: mockGetEmotionBehaviorRules,
  bindSessionAgent: mockBindSessionAgent,
  unbindSessionAgent: mockUnbindSessionAgent,
  getInteractionHotspots: mockGetInteractionHotspots,
  getAgentMonologues: mockGetAgentMonologues,
  getAutonomyLogs: mockGetAutonomyLogs,
  fetchStateAwareness: mockFetchStateAwareness,
}))

vi.mock('@/lib/chat-management-api', () => ({
  getChatStreams: mockGetChatStreams,
}))

vi.mock('@/lib/migration-api', () => ({
  getMigrationStates: mockGetMigrationStates,
  advanceMigration: mockAdvanceMigration,
}))

import { InnerWorldView } from '../components/inner-world/inner-world-view'
import type { AgentConfigInfo, EmotionStateInfo, SessionAgentInfo } from '@/lib/agent-api'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeAgent(): AgentConfigInfo {
  return {
    agent_id: 'agent-a',
    display_name: '麦麦',
    personality: '温柔',
    reply_style: '活泼',
    is_default: false,
    color: '#55AB49',
    emotion_baseline: { happy: 0.5, calm: 0.4 },
    emotion_decay_rate: 0.9,
    relationship_growth_rate: 0.1,
    talk_value_modifier: 1.0,
    memory_focus_areas: ['chat'],
    internal_relationships: [
      {
        target_agent_id: 'agent-b',
        relationship_type: 'friend',
        attitude: 'warm',
        interaction_style: 'casual',
        mention_tendency: 0.6,
        anti_mechanization: 'none',
      },
    ],
    anti_mechanization_rules: ['不要重复'],
  }
}

function makeEmotion(): EmotionStateInfo {
  return {
    agent_id: 'agent-a',
    emotions: { happy: 60, calm: 40 },
    dominant_emotion: 'happy',
    dominant_emotion_label: '开心',
    emotion_labels: { happy: '开心', calm: '平静' },
  }
}

function makeSession(): SessionAgentInfo {
  return {
    session_id: 'sess-1',
    display_name: '闲聊群',
    agent_id: 'agent-a',
    agent_display_name: '麦麦',
    status: 'active',
    is_primary: true,
    last_spoke_at: '2026-08-11T10:00:00Z',
    cohabitants: [],
    vitality_value: 80,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetAgentList.mockResolvedValue([makeAgent()])
  mockGetBatchEmotions.mockResolvedValue({
    'agent-a': { emotions: { happy: 60 }, dominant_emotion: 'happy', dominant_emotion_label: '开心', emotion_labels: {} },
  })
  mockGetBatchRelationships.mockResolvedValue({
    data: { 'agent-a': [{ user_id: 'u1', level: 1, level_name: '认识', score: 400, total_interactions: 3 }] },
    internal_relationships_summary: {},
  })
  mockGetBatchSessionCounts.mockResolvedValue({ 'agent-a': 1 })
  mockGetBatchLatestSubAgentRecords.mockResolvedValue({ 'agent-a': null })
  mockGetAgentDetail.mockResolvedValue(makeAgent())
  mockGetAgentEmotion.mockResolvedValue(makeEmotion())
  mockGetAgentRelationships.mockResolvedValue([{ user_id: 'u1', level: 1, level_name: '认识', score: 400, total_interactions: 3 }])
  mockGetSessionsByAgent.mockResolvedValue([makeSession()])
  mockGetSubAgentRecords.mockResolvedValue([])
  mockGetEmotionBehaviorRules.mockResolvedValue([])
  mockBindSessionAgent.mockResolvedValue(undefined)
  mockUnbindSessionAgent.mockResolvedValue(undefined)
  mockGetInteractionHotspots.mockResolvedValue([])
  mockGetAgentMonologues.mockResolvedValue([])
  mockGetAutonomyLogs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
  mockFetchStateAwareness.mockResolvedValue({
    session_id: 'sess-1',
    cohabitant_entries: [
      {
        agent_id: 'agent-b',
        display_name: '小助手',
        state: 'standby',
        vitality_level: 'moderate',
        emotion_tendency: '平静',
      },
    ],
    summary_preview: '',
    active_rules: [],
  })
  mockGetChatStreams.mockResolvedValue([])
  mockGetMigrationStates.mockResolvedValue([])
  mockAdvanceMigration.mockResolvedValue({ plugin_id: 'p1', current_phase: 'coexistence' })
})

describe('InnerWorldView', () => {
  it('加载完成后渲染 identity header + 7 个 tab', async () => {
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    expect(screen.getByText('agent.innerWorld.loading')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })

    for (const key of [
      'agent.innerWorld.subView.emotion',
      'agent.innerWorld.subView.relationship',
      'agent.innerWorld.subView.memory',
      'agent.innerWorld.subView.timeline',
      'agent.innerWorld.subView.sessions',
      'agent.monologue.panel.title',
      'agent.innerWorld.subView.autonomy',
    ]) {
      expect(screen.getByRole('tab', { name: key })).toBeInTheDocument()
    }
  })

  it('默认 emotion tab 渲染 EmotionLandscape（雷达 + 强度 + 基线）', async () => {
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })

    expect(screen.getByText('agent.emotionLandscape.radarTitle')).toBeInTheDocument()
    expect(screen.getByText('agent.emotionLandscape.barTitle')).toBeInTheDocument()
    expect(screen.getByText('agent.emotionLandscape.baselineShift')).toBeInTheDocument()
  })

  it('点击 relationship tab 渲染 RelationshipNetwork', async () => {
    const user = userEvent.setup()
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('tab', { name: 'agent.innerWorld.subView.relationship' }))

    await waitFor(() => {
      expect(screen.getByText('agent.relationshipNetwork.distribution')).toBeInTheDocument()
    })
    expect(screen.getByText('agent.relationshipNetwork.ranking')).toBeInTheDocument()
    expect(mockGetInteractionHotspots).toHaveBeenCalled()
  })

  it('点击 memory tab 渲染 MemoryGarden（焦点区域 + 内在活动）', async () => {
    const user = userEvent.setup()
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('tab', { name: 'agent.innerWorld.subView.memory' }))

    expect(screen.getByText('agent.memoryGarden.focusAreas')).toBeInTheDocument()
    expect(screen.getByText('agent.memoryGarden.innerActivity')).toBeInTheDocument()
  })

  it('点击 timeline tab 渲染 LifeTimeline（情绪转向事件）', async () => {
    const user = userEvent.setup()
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('tab', { name: 'agent.innerWorld.subView.timeline' }))

    await waitFor(() => {
      expect(screen.getByText('agent.lifeTimeline.emotionShift')).toBeInTheDocument()
    })
  })

  it('点击 sessions tab 渲染 ActiveSessions（会话标题 + 绑定按钮）', async () => {
    const user = userEvent.setup()
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('tab', { name: 'agent.innerWorld.subView.sessions' }))

    expect(screen.getByText((c) => c.startsWith('agent.activeSessions.title'))).toBeInTheDocument()
    expect(screen.getByText('agent.activeSessions.bindSession')).toBeInTheDocument()
    expect(screen.getByText('闲聊群')).toBeInTheDocument()
  })

  it('点击 monologue tab 渲染 MonologuePanel（空态）', async () => {
    const user = userEvent.setup()
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('tab', { name: 'agent.monologue.panel.title' }))

    await waitFor(() => {
      expect(screen.getByText('agent.monologue.panel.empty')).toBeInTheDocument()
    })
    expect(mockGetAgentMonologues).toHaveBeenCalledWith('agent-a', 10)
  })

  it('点击 autonomy tab 渲染 AutonomyLogPanel + StateAwarenessPanel', async () => {
    const user = userEvent.setup()
    render(<InnerWorldView agentId="agent-a" onBack={() => {}} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('tab', { name: 'agent.innerWorld.subView.autonomy' }))

    await waitFor(() => {
      expect(screen.getByText('agent.autonomyLogs.title')).toBeInTheDocument()
    })
    expect(mockGetAutonomyLogs).toHaveBeenCalledWith(expect.objectContaining({ agent_id: 'agent-a' }))
    await waitFor(() => {
      expect(screen.getByText('agent.stateAwareness.title')).toBeInTheDocument()
    })
    expect(mockFetchStateAwareness).toHaveBeenCalledWith('sess-1')
  })

  it('返回按钮触发 onBack', async () => {
    const user = userEvent.setup()
    const onBack = vi.fn()
    render(<InnerWorldView agentId="agent-a" onBack={onBack} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '' }))

    expect(onBack).toHaveBeenCalled()
  })
})