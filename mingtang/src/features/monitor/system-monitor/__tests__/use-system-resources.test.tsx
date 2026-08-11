/**
 * useSystemResources 测试（T1-6-3 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - REST 初始加载（getSystemResources）
 * - ws `system_resources`（update/snapshot 事件 → data 更新）
 * - 连接状态：connected 订阅 + 断开轮询兜底
 */
import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { WsEventEnvelope } from '@/lib/unified-ws'
import type { SystemResources } from '@/lib/system-api'

const { mockGetSystemResources, mockUnifiedWs, emitEvent, emitConnection } = vi.hoisted(() => {
  const listeners: Array<(msg: WsEventEnvelope) => void> = []
  const connListeners: Array<(connected: boolean) => void> = []
  return {
    mockGetSystemResources: vi.fn(),
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

vi.mock('@/lib/system-api', () => ({
  getSystemResources: mockGetSystemResources,
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: mockUnifiedWs,
}))

import { useSystemResources } from '../hooks/use-system-resources'

function makeResources(overrides: Partial<SystemResources> = {}): SystemResources {
  return {
    cpu_percent: 30,
    memory_percent: 50,
    memory_used: 4096 * 1024 * 1024,
    memory_total: 8192 * 1024 * 1024,
    disk_percent: 60,
    disk_used: 100 * 1024 * 1024 * 1024,
    disk_total: 200 * 1024 * 1024 * 1024,
    database_size: 1024 * 1024 * 1024,
    timestamp: Date.now(),
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetSystemResources.mockResolvedValue(makeResources())
})

describe('useSystemResources', () => {
  it('REST 初始加载 → data 填充', async () => {
    const { result } = renderHook(() => useSystemResources())

    await waitFor(() => {
      expect(result.current.data?.cpu_percent).toBe(30)
    })
    expect(mockGetSystemResources).toHaveBeenCalled()
  })

  it('ws update 事件 → data 更新', async () => {
    const { result } = renderHook(() => useSystemResources())

    await waitFor(() => {
      expect(result.current.data).not.toBeNull()
    })

    act(() => {
      emitEvent({
        op: 'event',
        domain: 'system_resources',
        event: 'update',
        data: { ...makeResources({ cpu_percent: 80 }) },
      })
    })

    expect(result.current.data?.cpu_percent).toBe(80)
  })

  it('ws snapshot 事件 → data 更新', async () => {
    const { result } = renderHook(() => useSystemResources())

    await waitFor(() => {
      expect(result.current.data).not.toBeNull()
    })

    act(() => {
      emitEvent({
        op: 'event',
        domain: 'system_resources',
        event: 'snapshot',
        data: { ...makeResources({ memory_percent: 90 }) },
      })
    })

    expect(result.current.data?.memory_percent).toBe(90)
  })

  it('ws 非 system_resources 事件不更新 data', async () => {
    const { result } = renderHook(() => useSystemResources())

    await waitFor(() => {
      expect(result.current.data).not.toBeNull()
    })

    act(() => {
      emitEvent({
        op: 'event',
        domain: 'llm_stats',
        event: 'call_completed',
        data: { model_name: 'gpt-4o' },
      })
    })

    expect(result.current.data?.cpu_percent).toBe(30)
  })

  it('连接状态：connected → 订阅 + isConnected true', async () => {
    mockUnifiedWs.getStatus.mockReturnValue('connected')
    const { result } = renderHook(() => useSystemResources())

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
    expect(mockUnifiedWs.subscribe).toHaveBeenCalledWith('system_resources', 'main')
  })

  it('onConnectionChange 断开 → isConnected false', async () => {
    const { result } = renderHook(() => useSystemResources())

    act(() => emitConnection(true))
    expect(result.current.isConnected).toBe(true)
    expect(mockUnifiedWs.subscribe).toHaveBeenCalledWith('system_resources', 'main')

    act(() => emitConnection(false))
    expect(result.current.isConnected).toBe(false)
  })

  it('REST 失败 → error 设置', async () => {
    mockGetSystemResources.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useSystemResources())

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })
    expect(result.current.data).toBeNull()
  })
})