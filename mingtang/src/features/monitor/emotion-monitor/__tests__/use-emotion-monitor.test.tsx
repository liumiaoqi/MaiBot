/**
 * useEmotionMonitor 测试（T1-3-2 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 多 agent 数据聚合（getAgentList + getAgentEmotion → allEmotions）
 * - React 19 适配：initialAgentId seed 用渲染期 setState（非 effect 内 setState）
 * - 视图状态（viewMode / autoRefresh）切换
 * - 事件触发用 act() 包裹（R3-W-10 教训）
 */
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetAgentList, mockGetAgentEmotion } = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetAgentEmotion: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getAgentEmotion: mockGetAgentEmotion,
}))

import { useEmotionMonitor } from '../hooks/use-emotion-monitor'
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

describe('useEmotionMonitor', () => {
  it('初始状态：grid 视图 + 空数据', () => {
    const { result } = renderHook(() => useEmotionMonitor(), { wrapper: createWrapper() })

    expect(result.current.viewMode).toBe('grid')
    expect(result.current.autoRefresh).toBe(false)
    expect(result.current.agents).toEqual([])
    expect(result.current.allEmotions).toEqual({})
  })

  it('加载后返回 agents 列表', async () => {
    const { result } = renderHook(() => useEmotionMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    expect(result.current.agents[0].display_name).toBe('麦麦')
  })

  it('allEmotions 聚合多 agent 情绪', async () => {
    const { result } = renderHook(() => useEmotionMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(Object.keys(result.current.allEmotions)).toHaveLength(2)
    })
    expect(result.current.allEmotions['agent-a'].dominant_emotion).toBe('happy')
    expect(result.current.allEmotions['agent-b'].dominant_emotion).toBe('calm')
  })

  it('initialAgentId 匹配时 seed detail 视图（渲染期 setState）', async () => {
    const { result } = renderHook(() => useEmotionMonitor('agent-a'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.selectedAgentId).toBe('agent-a')
    })
    expect(result.current.viewMode).toBe('detail')
    expect(result.current.selectedAgent?.display_name).toBe('麦麦')
  })

  it('initialAgentId 不匹配时保持 grid 视图', async () => {
    const { result } = renderHook(() => useEmotionMonitor('unknown-agent'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    expect(result.current.selectedAgentId).toBeNull()
    expect(result.current.viewMode).toBe('grid')
  })

  it('setViewMode / setAutoRefresh 状态切换', () => {
    const { result } = renderHook(() => useEmotionMonitor(), { wrapper: createWrapper() })

    act(() => result.current.setViewMode('detail'))
    act(() => result.current.setAutoRefresh(true))

    expect(result.current.viewMode).toBe('detail')
    expect(result.current.autoRefresh).toBe(true)
  })

  it('setSelectedAgentId 更新选中智能体', () => {
    const { result } = renderHook(() => useEmotionMonitor(), { wrapper: createWrapper() })

    act(() => result.current.setSelectedAgentId('agent-b'))

    expect(result.current.selectedAgentId).toBe('agent-b')
  })
})