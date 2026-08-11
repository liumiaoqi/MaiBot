/**
 * useBatchAgentData 测试（T2-3-1 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 批量数据获取（getAgentList/batchGetEmotions/batchGetRelationships/batchGetSessionCounts/batchGetLatestSubAgentRecords）
 * - 部分接口失败降级（catch → 空对象）
 * - refetch 触发重新请求
 */
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const {
  mockGetAgentList,
  mockGetBatchEmotions,
  mockGetBatchRelationships,
  mockGetBatchSessionCounts,
  mockGetBatchLatestSubAgentRecords,
} = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetBatchEmotions: vi.fn(),
  mockGetBatchRelationships: vi.fn(),
  mockGetBatchSessionCounts: vi.fn(),
  mockGetBatchLatestSubAgentRecords: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getBatchEmotions: mockGetBatchEmotions,
  getBatchRelationships: mockGetBatchRelationships,
  getBatchSessionCounts: mockGetBatchSessionCounts,
  getBatchLatestSubAgentRecords: mockGetBatchLatestSubAgentRecords,
}))

import { useBatchAgentData } from '../hooks/use-batch-agent-data'
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
  mockGetAgentList.mockResolvedValue([makeAgent('agent-a'), makeAgent('agent-b')])
  mockGetBatchEmotions.mockResolvedValue({ 'agent-a': { emotions: { happy: 0.8 }, dominant_emotion: 'happy', dominant_emotion_label: '开心', emotion_labels: {} } })
  mockGetBatchRelationships.mockResolvedValue({
    data: { 'agent-a': [{ user_id: 'u1', level: 2, level_name: '认识', score: 600, total_interactions: 5 }] },
    internal_relationships_summary: { 'agent-b': [{ target_agent_id: 'agent-a', relationship_type: 'friend', mention_tendency: 0.7 }] },
  })
  mockGetBatchSessionCounts.mockResolvedValue({ 'agent-a': 3, 'agent-b': 1 })
  mockGetBatchLatestSubAgentRecords.mockResolvedValue({
    'agent-a': { id: 1, subagent_id: 's1', agent_id: 'agent-a', subagent_type: 'self_reflection', status: 'completed', completed_at: null, result_summary: '内省' },
    'agent-b': null,
  })
})

describe('useBatchAgentData', () => {
  it('初始状态：空数据 + loading', () => {
    const { result } = renderHook(() => useBatchAgentData(), { wrapper: createWrapper() })
    expect(result.current.agents).toEqual([])
    expect(result.current.emotions).toEqual({})
    expect(result.current.isLoading).toBe(true)
  })

  it('加载后聚合全部批量数据', async () => {
    const { result } = renderHook(() => useBatchAgentData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    expect(result.current.relationships['agent-a']).toHaveLength(1)
    expect(result.current.internalRelationshipsSummary['agent-b']).toHaveLength(1)
    expect(result.current.sessionCounts['agent-a']).toBe(3)
    expect(result.current.latestSubAgentRecords['agent-a']?.subagent_type).toBe('self_reflection')
    expect(result.current.isLoading).toBe(false)
  })

  it('批量接口失败时降级为空对象', async () => {
    mockGetBatchEmotions.mockRejectedValue(new Error('boom'))
    mockGetBatchSessionCounts.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useBatchAgentData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    expect(result.current.emotions).toEqual({})
    expect(result.current.sessionCounts).toEqual({})
    expect(result.current.error).toBeNull()
  })

  it('refetch 触发重新请求', async () => {
    const { result } = renderHook(() => useBatchAgentData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    const callsBefore = mockGetAgentList.mock.calls.length

    act(() => result.current.refetch())

    await waitFor(() => {
      expect(mockGetAgentList.mock.calls.length).toBeGreaterThan(callsBefore)
    })
  })
})