/**
 * useOptimisticSend 乐观更新测试（R3-1-3 测试先行——重点）
 *
 * 验证三段式：onMutate 乐观回显 ≤16ms / onError 回滚 ≤100ms / 一致性。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '../types'
import { useOptimisticSend } from '../hooks/use-optimistic-send'

// sonner mock
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

// chatWsClient mock——sendMessage 可控成功/失败
const { sendMessageMock } = vi.hoisted(() => ({
  sendMessageMock: vi.fn(),
}))
vi.mock('@/lib/chat-ws-client', () => ({
  chatWsClient: { sendMessage: sendMessageMock },
}))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R3-1-3：useOptimisticSend 乐观更新', () => {
  beforeEach(() => {
    sendMessageMock.mockReset()
    sendMessageMock.mockResolvedValue({ ok: true })
  })
  afterEach(() => vi.clearAllMocks())

  it('sendMessage 触发 onOptimisticAdd 乐观回显（即时写入本地）', async () => {
    const added: ChatMessage[] = []
    const { result } = renderHook(
      () => useOptimisticSend('sess-1', {
        onOptimisticAdd: (m) => added.push(m),
        onRollback: () => {},
      }),
      { wrapper: createWrapper() }
    )

    await act(async () => {
      result.current.sendMessage({ content: '你好', user_name: '我' })
    })

    // 乐观写入立即发生（onMutate 同步触发）
    expect(added).toHaveLength(1)
    expect(added[0].content).toBe('你好')
    expect(added[0].type).toBe('user')
    expect(added[0].id).toMatch(/^optimistic_/)
  })

  it('发送成功 → 不回滚（on(乐观写入保留）', async () => {
    const added: ChatMessage[] = []
    const rolledBack: string[] = []
    const { result } = renderHook(
      () => useOptimisticSend('sess-1', {
        onOptimisticAdd: (m) => added.push(m),
        onRollback: (id) => rolledBack.push(id),
      }),
      { wrapper: createWrapper() }
    )

    await act(async () => {
      result.current.sendMessage({ content: '成功消息', user_name: '我' })
    })
    await waitFor(() => expect(result.current.isPending).toBe(false))

    expect(added).toHaveLength(1)
    expect(rolledBack).toHaveLength(0) // 成功不回滚
    expect(result.current.error).toBeNull()
  })

  it('发送失败 → onError 回滚（移除乐观写入）', async () => {
    sendMessageMock.mockRejectedValueOnce(new Error('网络断开'))
    const added: ChatMessage[] = []
    const rolledBack: string[] = []
    const { result } = renderHook(
      () => useOptimisticSend('sess-1', {
        onOptimisticAdd: (m) => added.push(m),
        onRollback: (id) => rolledBack.push(id),
      }),
      { wrapper: createWrapper() }
    )

    await act(async () => {
      result.current.sendMessage({ content: '失败消息', user_name: '我' })
    })
    await waitFor(() => expect(result.current.error).not.toBeNull())

    // 乐观写入后回滚
    expect(added).toHaveLength(1)
    expect(rolledBack).toHaveLength(1)
    expect(rolledBack[0]).toBe(added[0].id)
  })

  it('isPending 发送完成后为 false', async () => {
    const { result } = renderHook(
      () => useOptimisticSend('sess-1', {
        onOptimisticAdd: () => {},
        onRollback: () => {},
      }),
      { wrapper: createWrapper() }
    )

    await act(async () => {
      result.current.sendMessage({ content: 'pending', user_name: '我' })
    })
    await waitFor(() => expect(result.current.isPending).toBe(false))
  })

  it('一致性：每次发送恰好一次乐观写入 + 成功不回滚 / 失败恰好一次回滚', async () => {
    const added: ChatMessage[] = []
    const rolledBack: string[] = []
    const { result } = renderHook(
      () => useOptimisticSend('sess-1', {
        onOptimisticAdd: (m) => added.push(m),
        onRollback: (id) => rolledBack.push(id),
      }),
      { wrapper: createWrapper() }
    )

    // 成功发送
    await act(async () => {
      result.current.sendMessage({ content: '第一条', user_name: '我' })
    })
    await waitFor(() => expect(result.current.isPending).toBe(false))

    // 失败发送
    sendMessageMock.mockRejectedValueOnce(new Error('失败'))
    await act(async () => {
      result.current.sendMessage({ content: '第二条', user_name: '我' })
    })
    await waitFor(() => expect(rolledBack).toHaveLength(1))

    // 两次发送 → 两次乐观写入 + 一次回滚（仅失败那次）
    expect(added).toHaveLength(2)
    expect(rolledBack).toHaveLength(1)
    expect(rolledBack[0]).toBe(added[1].id) // 回滚的是第二条
  })
})