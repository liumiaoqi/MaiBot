/**
 * useLocalCacheMetrics 测试（§4.3.1 测试先行）
 *
 * 核心验证：
 * - useQuery 化后 staleTime=15min 缓存命中
 * - fetchLocalCacheStats() invalidateQueries 触发刷新
 */
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetLocalCacheStats } = vi.hoisted(() => ({
  mockGetLocalCacheStats: vi.fn(),
}))

vi.mock('@/lib/system-api', () => ({
  getLocalCacheStats: mockGetLocalCacheStats,
  LocalCacheStats: {},
}))

import { useLocalCacheMetrics } from '../use-local-cache-metrics'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

const mockStats = {
  directories: [
    { key: 'chat-records', label: '聊天记录', path: '/data/chat', exists: true, file_count: 100, total_size: 50 * 1024 * 1024, db_records: 0 },
    { key: 'memory', label: '记忆', path: '/data/memory', exists: true, file_count: 200, total_size: 30 * 1024 * 1024, db_records: 0 },
    { key: 'logs', label: '日志', path: '/data/logs', exists: true, file_count: 500, total_size: 20 * 1024 * 1024, db_records: 0 },
  ],
  database: {
    files: [],
    tables: [],
    total_size: 1024 * 1024 * 100,
    page_size: 4096,
    page_count: 25600,
    freelist_count: 0,
    free_size: 0,
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetLocalCacheStats.mockResolvedValue(mockStats)
})

describe('useLocalCacheMetrics', () => {
  it('初始状态：null + loading', () => {
    const { result } = renderHook(() => useLocalCacheMetrics(), { wrapper: createWrapper() })
    expect(result.current.localCacheStats).toBeNull()
    expect(result.current.isLocalCacheStatsLoading).toBe(true)
  })

  it('加载后返回本地缓存统计', async () => {
    const { result } = renderHook(() => useLocalCacheMetrics(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.localCacheStats).not.toBeNull()
    })
    expect(result.current.localCacheStats?.directories).toHaveLength(3)
    expect(result.current.localCacheStats?.database.total_size).toBe(mockStats.database.total_size)
    expect(result.current.isLocalCacheStatsLoading).toBe(false)
  })

  it('fetchLocalCacheStats 触发 invalidateQueries 重新请求', async () => {
    const { result } = renderHook(() => useLocalCacheMetrics(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.localCacheStats).not.toBeNull()
    })
    const callsBefore = mockGetLocalCacheStats.mock.calls.length

    const updatedStats = { ...mockStats, total_size: 200 * 1024 * 1024 }
    mockGetLocalCacheStats.mockResolvedValue(updatedStats)

    await act(async () => {
      await result.current.fetchLocalCacheStats()
    })

    await waitFor(() => {
      expect(mockGetLocalCacheStats.mock.calls.length).toBeGreaterThan(callsBefore)
    })
  })

  it('加载失败时 localCacheStats=null + loading=false', async () => {
    mockGetLocalCacheStats.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useLocalCacheMetrics(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLocalCacheStatsLoading).toBe(false)
    })
    expect(result.current.localCacheStats).toBeNull()
  })
})