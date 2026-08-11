/**
 * useRelationshipMonitor 测试（T1-4-2 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 关系数据聚合（getAgentList + getAgentRelationships → allRelationships）
 * - React 19 适配：initialAgentId seed 用渲染期 setState（非 effect 内 setState）
 * - totalRelationships 汇总 + selectedRelationships 随选中变化
 */
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetAgentList, mockGetAgentRelationships } = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetAgentRelationships: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getAgentRelationships: mockGetAgentRelationships,
}))

import { useRelationshipMonitor } from '../hooks/use-relationship-monitor'
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

describe('useRelationshipMonitor', () => {
  it('初始状态：无选中 + 空数据', () => {
    const { result } = renderHook(() => useRelationshipMonitor(), { wrapper: createWrapper() })

    expect(result.current.selectedAgentId).toBeNull()
    expect(result.current.agents).toEqual([])
    expect(result.current.allRelationships).toEqual({})
    expect(result.current.totalRelationships).toBe(0)
  })

  it('加载后返回 agents 列表', async () => {
    const { result } = renderHook(() => useRelationshipMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    expect(result.current.agents[0].display_name).toBe('麦麦')
  })

  it('allRelationships 聚合多 agent 关系 + totalRelationships 汇总', async () => {
    const { result } = renderHook(() => useRelationshipMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(Object.keys(result.current.allRelationships)).toHaveLength(2)
    })
    expect(result.current.allRelationships['agent-a']).toHaveLength(2)
    expect(result.current.allRelationships['agent-b']).toHaveLength(1)
    expect(result.current.totalRelationships).toBe(3)
  })

  it('单 agent 关系请求失败时降级为空数组', async () => {
    mockGetAgentRelationships.mockImplementation((agentId: string) =>
      agentId === 'agent-a'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve([makeRelationship('user-3', 1, 500)])
    )

    const { result } = renderHook(() => useRelationshipMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(Object.keys(result.current.allRelationships)).toHaveLength(2)
    })
    expect(result.current.allRelationships['agent-a']).toEqual([])
    expect(result.current.totalRelationships).toBe(1)
  })

  it('initialAgentId 匹配时 seed 选中（渲染期 setState）', async () => {
    const { result } = renderHook(() => useRelationshipMonitor('agent-a'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.selectedAgentId).toBe('agent-a')
    })
    expect(result.current.selectedAgent?.display_name).toBe('麦麦')
  })

  it('initialAgentId 不匹配时保持无选中', async () => {
    const { result } = renderHook(() => useRelationshipMonitor('unknown-agent'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })
    expect(result.current.selectedAgentId).toBeNull()
  })

  it('setSelectedAgentId 更新选中 + selectedRelationships 随选中变化', async () => {
    const { result } = renderHook(() => useRelationshipMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })

    act(() => result.current.setSelectedAgentId('agent-b'))
    expect(result.current.selectedAgentId).toBe('agent-b')

    await waitFor(() => {
      expect(result.current.selectedRelationships).toHaveLength(1)
    })
    expect(result.current.selectedRelationships[0].user_id).toBe('user-3')
  })

  it('refresh 触发 refetch（agents + allRelationships）', async () => {
    const { result } = renderHook(() => useRelationshipMonitor(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(2)
    })

    act(() => result.current.refresh())

    await waitFor(() => {
      expect(mockGetAgentList.mock.calls.length).toBeGreaterThanOrEqual(3)
    })
  })
})