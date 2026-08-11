/**
 * useInnerWorldData 测试（T2-3-3 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 内在世界数据（getAgentDetail/getAgentEmotion/getAgentRelationships/getSubAgentRecords/getEmotionBehaviorRules/getSessionsByAgent）
 * - agentId 为 null 时禁用全部查询
 * - isCoreLoading / isAuxLoading / isLoading 分级
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const {
  mockGetAgentDetail,
  mockGetAgentEmotion,
  mockGetAgentRelationships,
  mockGetSessionsByAgent,
  mockGetSubAgentRecords,
  mockGetEmotionBehaviorRules,
} = vi.hoisted(() => ({
  mockGetAgentDetail: vi.fn(),
  mockGetAgentEmotion: vi.fn(),
  mockGetAgentRelationships: vi.fn(),
  mockGetSessionsByAgent: vi.fn(),
  mockGetSubAgentRecords: vi.fn(),
  mockGetEmotionBehaviorRules: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentDetail: mockGetAgentDetail,
  getAgentEmotion: mockGetAgentEmotion,
  getAgentRelationships: mockGetAgentRelationships,
  getSessionsByAgent: mockGetSessionsByAgent,
  getSubAgentRecords: mockGetSubAgentRecords,
  getEmotionBehaviorRules: mockGetEmotionBehaviorRules,
}))

import { useInnerWorldData } from '../hooks/use-inner-world-data'
import type { AgentConfigInfo } from '@/lib/agent-api'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeAgent(id: string): AgentConfigInfo {
  return {
    agent_id: id,
    display_name: `智能体-${id}`,
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
  mockGetAgentDetail.mockResolvedValue(makeAgent('agent-a'))
  mockGetAgentEmotion.mockResolvedValue({ agent_id: 'agent-a', emotions: { happy: 0.8 }, dominant_emotion: 'happy', dominant_emotion_label: '开心', emotion_labels: {} })
  mockGetAgentRelationships.mockResolvedValue([{ user_id: 'u1', level: 2, level_name: '认识', score: 600, total_interactions: 5 }])
  mockGetSessionsByAgent.mockResolvedValue([])
  mockGetSubAgentRecords.mockResolvedValue([])
  mockGetEmotionBehaviorRules.mockResolvedValue([])
})

describe('useInnerWorldData', () => {
  it('agentId 为 null 时全部禁用（空数据 + 无请求）', () => {
    const { result } = renderHook(() => useInnerWorldData(null), { wrapper: createWrapper() })

    expect(result.current.agent).toBeNull()
    expect(result.current.relationships).toEqual([])
    expect(result.current.isLoading).toBe(false)
    expect(mockGetAgentDetail).not.toHaveBeenCalled()
  })

  it('agentId 有效时加载全部数据', async () => {
    const { result } = renderHook(() => useInnerWorldData('agent-a'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agent?.display_name).toBe('智能体-agent-a')
    })
    expect(result.current.emotion?.dominant_emotion).toBe('happy')
    expect(result.current.relationships).toHaveLength(1)
    expect(mockGetAgentEmotion).toHaveBeenCalledWith('agent-a')
    expect(mockGetSubAgentRecords).toHaveBeenCalledWith({ agent_id: 'agent-a', limit: 10 })
  })

  it('isCoreLoading / isAuxLoading 分级', async () => {
    const { result } = renderHook(() => useInnerWorldData('agent-a'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agent).not.toBeNull()
    })
    expect(result.current.isCoreLoading).toBe(false)
    expect(result.current.isAuxLoading).toBe(false)
    expect(result.current.isLoading).toBe(false)
  })

  it('辅助查询失败时 error 暴露且不阻塞 agent', async () => {
    mockGetAgentRelationships.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useInnerWorldData('agent-a'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agent).not.toBeNull()
    })
    expect(result.current.relationships).toEqual([])
  })
})