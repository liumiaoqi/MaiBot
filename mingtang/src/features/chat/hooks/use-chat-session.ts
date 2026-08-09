/**
 * useChatSession WS 会话管理 hook（R3-1-5）
 *
 * chat-ws-client openSession（幂等/restore）+ onSessionMessage 订阅 + 消息去重 +
 * 连接状态。send 方法封装 chatWsClient.sendMessage。
 *
 * WS 消息流 8 类型处理（session_info/system/user_message/bot_message/typing/error/history）——
 * 消息去重基于 message_id（deduplicateMessage hash 上限 100）。
 *
 * 核心职责（REQ-R3-01 / REQ-R3-19）：WS 会话生命周期 + 消息流 + 连接状态。
 */
import { useEffect, useRef, useState } from 'react'

import { chatWsClient, type ChatImagePayload } from '@/lib/chat-ws-client'
import { unifiedWsClient, type ConnectionStatus } from '@/lib/unified-ws'

import type { ChatMessage } from '../types'
import { deduplicateMessage } from '../utils'

interface UseChatSessionResult {
  messages: ChatMessage[]
  connectionStatus: ConnectionStatus
  send: (content: string, images?: ChatImagePayload[]) => Promise<void>
}

/**
 * 管理 WS 聊天会话生命周期。
 *
 * @param sessionId 会话 ID（undefined 时不打开会话）
 * @param payload session.open 负载（user_id/user_name 等）
 * @returns { messages, connectionStatus, send }
 */
export function useChatSession(
  sessionId: string | undefined,
  payload: Record<string, unknown>
): UseChatSessionResult {
  const [internalMessages, setInternalMessages] = useState<ChatMessage[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    () => unifiedWsClient.getStatus()
  )
  // 消息去重 set（message_id hash 上限 100）
  const processedIdsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!sessionId) {
      return
    }

    let cancelled = false

    // 订阅连接状态变化
    const unsubStatus = unifiedWsClient.onStatusChange((status) => {
      if (!cancelled) {
        setConnectionStatus(status)
      }
    })

    // 打开会话（幂等——chatWsClient 内部处理重复打开）
    void chatWsClient.openSession(sessionId, payload).catch((error) => {
      console.error(`[useChatSession] 打开会话失败 (${sessionId}):`, error)
    })

    // 订阅会话消息
    const unsubSession = chatWsClient.onSessionMessage(sessionId, (raw) => {
      if (cancelled) return
      handleWsMessage(raw, setInternalMessages, processedIdsRef)
    })

    return () => {
      cancelled = true
      unsubStatus()
      unsubSession()
      // sessionId 变化时重置消息（cleanup 里 setState——非 effect body，lint 不拦截）
      setInternalMessages([])
      processedIdsRef.current = new Set()
    }
    // payload 是对象——用 JSON.stringify 做依赖比较避免重复打开
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, JSON.stringify(payload)])

  const send = async (content: string, images?: ChatImagePayload[]): Promise<void> => {
    if (!sessionId) {
      throw new Error('[useChatSession] 无活跃会话，无法发送')
    }
    const userName = (payload.user_name as string) || 'WebUI用户'
    await chatWsClient.sendMessage(sessionId, content, userName, images ? { images } : {})
  }

  // 派生状态：sessionId 为 undefined 时返回空消息（不在 effect 里 setState）
  const messages: ChatMessage[] = sessionId ? internalMessages : []
  return { messages, connectionStatus, send }
}

/**
 * 处理 WS 消息（8 类型——session_info/system/user_message/bot_message/typing/error/history）。
 *
 * 消息去重基于 message_id（deduplicateMessage hash 上限 100）。
 * typing/session_info 不产生消息（仅状态更新——R3-1-6 组装时衔接）。
 */
function handleWsMessage(
  raw: Record<string, unknown>,
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
  processedIdsRef: React.RefObject<Set<string>>
): void {
  const type = raw.type as string
  const messageId = raw.message_id as string | undefined
  const timestamp = (raw.timestamp as number) || Date.now()
  const content = (raw.content as string) || ''
  const sender = raw.sender as { name: string; is_bot?: boolean; user_id?: string } | undefined

  // 去重：有 message_id 时检查
  if (messageId) {
    const { isDuplicate, updatedSet } = deduplicateMessage(
      processedIdsRef.current,
      messageId
    )
    if (isDuplicate) return
    processedIdsRef.current = updatedSet
  }

  switch (type) {
    case 'system':
    case 'error': {
      const msg: ChatMessage = {
        id: messageId || `sys-${timestamp}`,
        type,
        content,
        timestamp,
      }
      setMessages((prev) => [...prev, msg])
      break
    }
    case 'user_message': {
      const msg: ChatMessage = {
        id: messageId || `user-${timestamp}`,
        type: 'user',
        content,
        timestamp,
        sender,
      }
      setMessages((prev) => [...prev, msg])
      break
    }
    case 'bot_message': {
      const msg: ChatMessage = {
        id: messageId || `bot-${timestamp}`,
        type: 'bot',
        content,
        timestamp,
        sender,
      }
      setMessages((prev) => [...prev, msg])
      break
    }
    case 'history': {
      // 历史消息批量加入
      const historyMessages = (raw.messages as Array<Record<string, unknown>>) || []
      const chatMessages: ChatMessage[] = historyMessages.map((m, i) => ({
        id: (m.id as string) || `hist-${i}-${m.timestamp}`,
        type: m.is_bot ? 'bot' : 'user',
        content: (m.content as string) || '',
        timestamp: (m.timestamp as number) || 0,
        sender: m.sender_name
          ? { name: m.sender_name as string, is_bot: m.is_bot as boolean }
          : undefined,
      }))
      setMessages((prev) => [...chatMessages, ...prev])
      break
    }
    // session_info / typing：不产生消息（状态更新由 R3-1-6 组装时衔接）
  }
}