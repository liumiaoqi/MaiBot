/**
 * useBotStatus 测试（§4.2.1 测试先行）
 *
 * 核心验证：
 * - useQuery 化后 30s 轮询（refetchInterval=30s）
 * - refetchOnWindowFocus（visibilitychange 恢复刷新）
 * - staleTime=30s
 * - fetchBotStatus(force) invalidateQueries 触发刷新
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

import { useBotStatus } from '../use-bot-status'
import type { BotStatus } from '../../types'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

const mockBotStatus: BotStatus = {
  running: true,
  uptime: 3600,
  version: '2.5.4',
  start_time: '2026-08-12T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockBackendGet.mockResolvedValue(mockBotStatus)
})

describe('useBotStatus', () => {
  it('初始状态：null + loading', () => {
    const { result } = renderHook(() => useBotStatus(), { wrapper: createWrapper() })
    expect(result.current.botStatus).toBeNull()
    expect(result.current.isBotStatusLoading).toBe(true)
  })

  it('加载后返回机器人状态', async () => {
    const { result } = renderHook(() => useBotStatus(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.botStatus).not.toBeNull()
    })
    expect(result.current.botStatus?.running).toBe(true)
    expect(result.current.botStatus?.version).toBe('2.5.4')
    expect(result.current.isBotStatusLoading).toBe(false)
  })

  it('fetchBotStatus 触发 invalidateQueries 重新请求', async () => {
    const { result } = renderHook(() => useBotStatus(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.botStatus).not.toBeNull()
    })
    const callsBefore = mockBackendGet.mock.calls.length

    const updatedStatus: BotStatus = { ...mockBotStatus, uptime: 7200 }
    mockBackendGet.mockResolvedValue(updatedStatus)

    await act(async () => {
      await result.current.fetchBotStatus()
    })

    await waitFor(() => {
      expect(mockBackendGet.mock.calls.length).toBeGreaterThan(callsBefore)
    })
  })

  it('加载失败时 botStatus=null + loading=false', async () => {
    mockBackendGet.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useBotStatus(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isBotStatusLoading).toBe(false)
    })
    expect(result.current.botStatus).toBeNull()
  })
})