/**
 * useLLMStats 测试（T1-6-2 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - REST 初始加载（statistics/dashboard + statistics/agents）
 * - ws `llm_stats` 增量更新（call_completed 事件触发 modelStats 状态合并）
 * - 连接状态（getStatus + onConnectionChange）
 */
import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { WsEventEnvelope } from '@/lib/unified-ws'

const { mockBackendGet, mockUnifiedWs, emitEvent, emitConnection } = vi.hoisted(() => {
  const listeners: Array<(msg: WsEventEnvelope) => void> = []
  const connListeners: Array<(connected: boolean) => void> = []
  return {
    mockBackendGet: vi.fn(),
    mockUnifiedWs: {
      getStatus: vi.fn(() => 'idle'),
      addEventListener: vi.fn((l: (msg: WsEventEnvelope) => void) => {
        listeners.push(l)
        return () => {}
      }),
      onConnectionChange: vi.fn((l: (connected: boolean) => void) => {
        connListeners.push(l)
        return () => {}
      }),
      subscribe: vi.fn(() => Promise.resolve({ ok: true })),
      unsubscribe: vi.fn(() => Promise.resolve(null)),
    },
    emitEvent: (msg: WsEventEnvelope) => {
      listeners.forEach((l) => l(msg))
    },
    emitConnection: (connected: boolean) => {
      connListeners.forEach((l) => l(connected))
    },
  }
})

vi.mock('@/lib/http', () => ({
  backendApi: { get: mockBackendGet },
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: mockUnifiedWs,
}))

import { useLLMStats } from '../hooks/use-llm-stats'

const dashboardData = {
  summary: {
    total_requests: 100,
    total_cost: 12.34,
    total_tokens: 50000,
    online_time: 3600,
    total_messages: 10,
    total_replies: 8,
    avg_response_time: 1.2,
    cost_per_hour: 0.5,
    tokens_per_hour: 1000,
  },
  model_stats: [
    {
      model_name: 'gpt-4o',
      request_count: 60,
      total_cost: 8,
      total_tokens: 30000,
      avg_response_time: 1.1,
    },
  ],
  hourly_data: [],
  daily_data: [],
  recent_activity: [],
}

const agentsData = {
  hours: 24,
  agents: [
    {
      agent_id: 'agent-a',
      request_count: 40,
      total_input_tokens: 10000,
      total_output_tokens: 5000,
      total_cost: 4,
      avg_response_time: 1.3,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  mockBackendGet.mockImplementation((path: string) => {
    if (path.includes('/statistics/dashboard')) return Promise.resolve(dashboardData)
    if (path.includes('/statistics/agents')) return Promise.resolve(agentsData)
    return Promise.reject(new Error('unknown path'))
  })
})

describe('useLLMStats', () => {
  it('初始加载：summary/modelStats/agentStats 从 REST 填充', async () => {
    const { result } = renderHook(() => useLLMStats())

    await waitFor(() => {
      expect(result.current.summary?.total_requests).toBe(100)
    })
    expect(result.current.modelStats).toHaveLength(1)
    expect(result.current.modelStats[0].model_name).toBe('gpt-4o')
    expect(result.current.agentStats).toHaveLength(1)
    expect(result.current.agentStats[0].agent_id).toBe('agent-a')
    expect(mockBackendGet).toHaveBeenCalledWith(
      expect.stringContaining('/statistics/dashboard'),
      expect.any(Object)
    )
  })

  it('ws call_completed 事件增量更新 modelStats（同 model_name 累加）', async () => {
    const { result } = renderHook(() => useLLMStats())

    await waitFor(() => {
      expect(result.current.modelStats).toHaveLength(1)
    })

    act(() => {
      emitEvent({
        op: 'event',
        domain: 'llm_stats',
        event: 'call_completed',
        data: { model_name: 'gpt-4o', cost: 0.5, prompt_tokens: 100, completion_tokens: 50, time_cost: 1.0 },
      })
    })

    expect(result.current.modelStats[0].request_count).toBe(61)
    expect(result.current.modelStats[0].total_cost).toBe(8.5)
    expect(result.current.modelStats[0].total_tokens).toBe(30150)
  })

  it('ws 非匹配 domain/event 不更新状态', async () => {
    const { result } = renderHook(() => useLLMStats())

    await waitFor(() => {
      expect(result.current.modelStats).toHaveLength(1)
    })

    act(() => {
      emitEvent({
        op: 'event',
        domain: 'system_resources',
        event: 'update',
        data: { cpu_percent: 90 },
      })
    })

    expect(result.current.modelStats[0].request_count).toBe(60)
  })

  it('连接状态：getStatus connected → isConnected true + 订阅 llm_stats', async () => {
    mockUnifiedWs.getStatus.mockReturnValue('connected')
    const { result } = renderHook(() => useLLMStats())

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
    expect(mockUnifiedWs.subscribe).toHaveBeenCalledWith('llm_stats', 'main')
  })

  it('onConnectionChange 连接/断开更新 isConnected', async () => {
    const { result } = renderHook(() => useLLMStats())

    act(() => emitConnection(true))
    expect(result.current.isConnected).toBe(true)
    expect(mockUnifiedWs.subscribe).toHaveBeenCalledWith('llm_stats', 'main')

    act(() => emitConnection(false))
    expect(result.current.isConnected).toBe(false)
  })

  it('setHours 变化触发重新加载', async () => {
    const { result } = renderHook(() => useLLMStats())

    await waitFor(() => {
      expect(result.current.summary?.total_requests).toBe(100)
    })

    act(() => result.current.setHours(6))

    await waitFor(() => {
      const dashboardCalls = mockBackendGet.mock.calls.filter((c) =>
        String(c[0]).includes('/statistics/dashboard')
      )
      expect(dashboardCalls.length).toBeGreaterThanOrEqual(2)
    })
    expect(result.current.hours).toBe(6)
  })

  it('exportCSV 调用 statistics/export 接口', async () => {
    mockBackendGet.mockImplementation((path: string) => {
      if (path.includes('/statistics/export')) return Promise.resolve(new Blob(['csv']))
      if (path.includes('/statistics/dashboard')) return Promise.resolve(dashboardData)
      if (path.includes('/statistics/agents')) return Promise.resolve(agentsData)
      return Promise.reject(new Error('unknown path'))
    })
    const { result } = renderHook(() => useLLMStats())

    await waitFor(() => {
      expect(result.current.summary).not.toBeNull()
    })

    await act(async () => {
      await result.current.exportCSV()
    })

    expect(mockBackendGet).toHaveBeenCalledWith(
      expect.stringContaining('/statistics/export'),
      expect.any(Object)
    )
  })
})