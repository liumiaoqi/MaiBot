/**
 * useChatSession WS 会话管理 hook 测试（R3-1-5 测试先行）
 *
 * 核心验收（REQ-R3-01 / REQ-R3-19）：
 * - openSession 打开会话
 * - onSessionMessage 订阅消息
 * - 消息去重（deduplicateMessage）
 * - 连接状态
 * - send 发送消息
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

import { useChatSession } from '../hooks/use-chat-session'

// 捕获 onSessionMessage 的 listener + onStatusChange 的 listener
let sessionListener: ((message: Record<string, unknown>) => void) | null = null
let statusListener: ((status: string) => void) | null = null
let sessionUnsubscribe: (() => void) | null = null
let statusUnsubscribe: (() => void) | null = null

vi.mock('@/lib/chat-ws-client', () => ({
  chatWsClient: {
    openSession: vi.fn(async () => {}),
    onSessionMessage: vi.fn((_sessionId: string, listener: (msg: never) => void) => {
      sessionListener = listener as typeof sessionListener
      sessionUnsubscribe = vi.fn(() => {})
      return sessionUnsubscribe
    }),
    sendMessage: vi.fn(async () => {}),
    closeSession: vi.fn(async () => {}),
  },
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: {
    onStatusChange: vi.fn((listener: (status: string) => void) => {
      statusListener = listener
      listener('connected')
      statusUnsubscribe = vi.fn(() => {})
      return statusUnsubscribe
    }),
    getStatus: vi.fn(() => 'connected'),
  },
}))

beforeEach(() => {
  sessionListener = null
  statusListener = null
  sessionUnsubscribe = null
  statusUnsubscribe = null
})

const payload = { user_id: 'u1', user_name: '测试' }

function emitMessage(msg: Record<string, unknown>) {
  act(() => {
    sessionListener?.(msg)
  })
}

describe('R3-1-5：useChatSession WS 会话管理', () => {
  it('sessionId 为 undefined 时不打开会话', () => {
    const { result } = renderHook(() => useChatSession(undefined, payload))
    expect(result.current.messages).toEqual([])
    expect(result.current.connectionStatus).toBe('connected')
  })

  it('打开会话 + 初始连接状态', async () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    await waitFor(() => {
      expect(result.current.connectionStatus).toBe('connected')
    })
  })

  it('接收 user_message 类型消息', () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    emitMessage({
      type: 'user_message',
      content: '你好',
      message_id: 'm1',
      timestamp: Date.now(),
      sender: { name: '用户', is_bot: false },
    })
    expect(result.current.messages.length).toBe(1)
    expect(result.current.messages[0].content).toBe('你好')
    expect(result.current.messages[0].type).toBe('user')
  })

  it('接收 bot_message 类型消息', () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    emitMessage({
      type: 'bot_message',
      content: '你好呀',
      message_id: 'm2',
      timestamp: Date.now(),
      sender: { name: 'MaiBot', is_bot: true },
    })
    expect(result.current.messages.length).toBe(1)
    expect(result.current.messages[0].content).toBe('你好呀')
    expect(result.current.messages[0].type).toBe('bot')
  })

  it('接收 system 消息', () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    emitMessage({
      type: 'system',
      content: '会话已开启',
      timestamp: Date.now(),
    })
    expect(result.current.messages.length).toBe(1)
    expect(result.current.messages[0].type).toBe('system')
  })

  it('接收 error 消息', () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    emitMessage({
      type: 'error',
      content: '出错了',
      timestamp: Date.now(),
    })
    expect(result.current.messages.length).toBe(1)
    expect(result.current.messages[0].type).toBe('error')
  })

  it('消息去重（相同 message_id 不重复加入）', () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    const ts = Date.now()
    emitMessage({
      type: 'user_message',
      content: '你好',
      message_id: 'm-dup',
      timestamp: ts,
      sender: { name: '用户', is_bot: false },
    })
    emitMessage({
      type: 'user_message',
      content: '你好',
      message_id: 'm-dup',
      timestamp: ts,
      sender: { name: '用户', is_bot: false },
    })
    expect(result.current.messages.length).toBe(1)
  })

  it('send 调用 chatWsClient.sendMessage', async () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    await act(async () => {
      await result.current.send('你好')
    })
    const { chatWsClient } = await import('@/lib/chat-ws-client')
    expect(chatWsClient.sendMessage).toHaveBeenCalledWith('s1', '你好', '测试', {})
  })

  it('send 带图片', async () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    const images = [{ name: 'a.png', mime_type: 'image/png', base64: 'xxx' }]
    await act(async () => {
      await result.current.send('看图', images)
    })
    const { chatWsClient } = await import('@/lib/chat-ws-client')
    expect(chatWsClient.sendMessage).toHaveBeenCalledWith('s1', '看图', '测试', { images })
  })

  it('连接状态变化时更新', () => {
    const { result } = renderHook(() => useChatSession('s1', payload))
    expect(result.current.connectionStatus).toBe('connected')
    act(() => {
      statusListener?.('disconnected')
    })
    expect(result.current.connectionStatus).toBe('disconnected')
  })
})
