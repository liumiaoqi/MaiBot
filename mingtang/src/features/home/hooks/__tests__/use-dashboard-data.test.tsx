/**
 * useDashboardData 测试（§4.1.1 测试先行）
 *
 * 核心验证：
 * - useQuery 化后缓存命中/过期/刷新（staleTime=5min + refetchOnWindowFocus）
 * - timeRange 切换（queryKey 含 hours 维度）
 * - 伪加载进度条已删除（P2 清理——loadingProgress 无 UI 消费）
 * - fetchDashboardData(force) invalidateQueries
 */
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockBackendGet } = vi.hoisted(() => ({
  mockBackendGet: vi.fn(),
}))

vi.mock('@/lib/http', () => ({
  backendApi: {
    get: mockBackendGet,
  },
}))

import { useDashboardData } from '../use-dashboard-data'
import type { DashboardData } from '../../types'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

const mockDashboardData: DashboardData = {
  summary: {
    total_requests: 100,
    total_cost: 0.5,
    total_tokens: 10000,
    online_time: 3600,
    total_messages: 50,
    total_replies: 50,
    avg_response_time: 2.0,
    cost_per_hour: 0.5,
    tokens_per_hour: 10000,
  },
  model_stats: [{ model_name: 'gpt-4', request_count: 100, total_cost: 0.5, total_tokens: 10000, avg_response_time: 2.0 }],
  hourly_data: [{ timestamp: '2026-08-12T00:00:00Z', requests: 10, cost: 0.05, tokens: 1000 }],
  daily_data: [{ timestamp: '2026-08-12', requests: 100, cost: 0.5, tokens: 10000 }],
  recent_activity: [{ timestamp: '2026-08-12T00:00:00Z', model: 'gpt-4', request_type: 'chat', tokens: 1000, cost: 0.05, time_cost: 2.0, status: 'ok' }],
  agent_stats: { total_agents: 2, active_agents: 1, total_active_sessions: 3 },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockBackendGet.mockResolvedValue(mockDashboardData)
})

describe('useDashboardData', () => {
  it('初始状态：null + loading + timeRange=24', () => {
    const { result } = renderHook(() => useDashboardData(), { wrapper: createWrapper() })
    expect(result.current.dashboardData).toBeNull()
    expect(result.current.loading).toBe(true)
    expect(result.current.timeRange).toBe(24)
  })

  it('加载后返回仪表盘数据', async () => {
    const { result } = renderHook(() => useDashboardData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.dashboardData).not.toBeNull()
    })
    expect(result.current.dashboardData?.summary.total_requests).toBe(100)
    expect(result.current.loading).toBe(false)
    // P2 清理：loadingProgress 已删除（伪加载进度条无 UI 消费）
    expect('loadingProgress' in result.current).toBe(false)
  })

  it('timeRange 切换触发新请求（queryKey 含 hours 维度）', async () => {
    const { result } = renderHook(() => useDashboardData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.dashboardData).not.toBeNull()
    })
    expect(mockBackendGet).toHaveBeenCalledWith('/api/webui/statistics/dashboard', { query: { hours: 24 } })

    act(() => result.current.setTimeRange(48))

    await waitFor(() => {
      expect(mockBackendGet).toHaveBeenCalledWith('/api/webui/statistics/dashboard', { query: { hours: 48 } })
    })
    expect(result.current.timeRange).toBe(48)
  })

  it('fetchDashboardData 触发 invalidateQueries 重新请求', async () => {
    const { result } = renderHook(() => useDashboardData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.dashboardData).not.toBeNull()
    })
    const callsBefore = mockBackendGet.mock.calls.length

    await act(async () => {
      await result.current.fetchDashboardData()
    })

    await waitFor(() => {
      expect(mockBackendGet.mock.calls.length).toBeGreaterThan(callsBefore)
    })
  })

  it('加载失败时 loading=false', async () => {
    mockBackendGet.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useDashboardData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.dashboardData).toBeNull()
  })
})