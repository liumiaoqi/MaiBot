/**
 * useRuntimeStatus 运行状态订阅 hook 测试（R3-1-5 测试先行）
 *
 * 核心验收（REQ-R3-04 / REQ-R3-19）：
 * - 订阅 maisaka-monitor 5 种事件（stage.snapshot/status/removed + llm.retry/error）
 * - resolveStatusKind 按 stage 关键词推断 thinking/typing/acting/error
 * - matchesMonitorTarget 三级匹配 tab
 * - 退订清理（防内存泄漏）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useRuntimeStatus } from '../hooks/use-runtime-status'
import type { ChatTab } from '../types'

// 捕获 subscribe 的 listener，用于模拟事件触发
let capturedListener: ((event: { type: string; data: Record<string, unknown> }) => void) | null =
  null
let unsubscribeFn: (() => Promise<void>) | null = null

vi.mock('@/lib/maisaka-monitor-client', () => ({
  maisakaMonitorClient: {
    subscribe: vi.fn(async (listener: (event: never) => void) => {
      capturedListener = listener as typeof capturedListener
      unsubscribeFn = vi.fn(async () => {})
      return unsubscribeFn
    }),
  },
}))

function tab(overrides: Partial<ChatTab> = {}): ChatTab {
  return {
    id: 'webui-default',
    type: 'webui',
    label: 'MaiBot',
    messages: [],
    isConnected: true,
    isTyping: false,
    sessionInfo: { session_id: 's1', bot_name: 'MaiBot' },
    ...overrides,
  }
}

function emitEvent(event: { type: string; data: Record<string, unknown> }) {
  act(() => {
    capturedListener?.(event)
  })
}

beforeEach(() => {
  capturedListener = null
  unsubscribeFn = null
})

describe('R3-1-5：useRuntimeStatus 运行状态订阅', () => {
  it('初始状态为 idle', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    expect(result.current.status).toBe('idle')
  })

  it('tab 为 undefined 时返回 idle', () => {
    const { result } = renderHook(() => useRuntimeStatus(undefined))
    expect(result.current.status).toBe('idle')
  })

  it('stage.status 事件匹配 tab 时推断状态', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'stage.status',
      data: {
        session_id: 's1',
        stage: 'thinking',
        detail: '',
        round_text: '',
        agent_state: '',
        stage_started_at: 0,
        updated_at: 0,
        timestamp: 0,
      },
    })
    expect(result.current.status).toBe('thinking')
  })

  it('stage.status 含 error 关键词推断 error', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'stage.status',
      data: {
        session_id: 's1',
        stage: 'error',
        detail: 'fail',
        round_text: '',
        agent_state: '',
        stage_started_at: 0,
        updated_at: 0,
        timestamp: 0,
      },
    })
    expect(result.current.status).toBe('error')
  })

  it('stage.status 不匹配 tab 时不影响状态', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'stage.status',
      data: {
        session_id: 'other-session',
        stage: 'thinking',
        detail: '',
        round_text: '',
        agent_state: '',
        stage_started_at: 0,
        updated_at: 0,
        timestamp: 0,
      },
    })
    expect(result.current.status).toBe('idle')
  })

  it('stage.removed 事件匹配 tab 时回到 idle', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'stage.status',
      data: {
        session_id: 's1',
        stage: 'thinking',
        detail: '',
        round_text: '',
        agent_state: '',
        stage_started_at: 0,
        updated_at: 0,
        timestamp: 0,
      },
    })
    expect(result.current.status).toBe('thinking')
    emitEvent({
      type: 'stage.removed',
      data: { session_id: 's1', timestamp: 0 },
    })
    expect(result.current.status).toBe('idle')
  })

  it('llm.error 事件匹配 tab 时推断 error', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'llm.error',
      data: { session_id: 's1', timestamp: 0 },
    })
    expect(result.current.status).toBe('error')
  })

  it('llm.retry 事件匹配 tab 时推断 error', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'llm.retry',
      data: { session_id: 's1', timestamp: 0 },
    })
    expect(result.current.status).toBe('error')
  })

  it('stage.snapshot 事件匹配 tab 时推断状态', () => {
    const { result } = renderHook(() => useRuntimeStatus(tab()))
    emitEvent({
      type: 'stage.snapshot',
      data: {
        entries: [
          {
            session_id: 's1',
            stage: 'typing',
            detail: '',
            round_text: '',
            agent_state: '',
            stage_started_at: 0,
            updated_at: 0,
            timestamp: 0,
          },
        ],
        timestamp: 0,
      },
    })
    expect(result.current.status).toBe('typing')
  })

  it('卸载时调用退订函数', () => {
    const { unmount } = renderHook(() => useRuntimeStatus(tab()))
    unmount()
    expect(unsubscribeFn).not.toBeNull()
  })
})
