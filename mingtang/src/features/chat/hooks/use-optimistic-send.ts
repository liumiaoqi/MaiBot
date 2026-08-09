/**
 * useOptimisticSend：聊天消息发送乐观更新 hook（REQ-R3-03 / REQ-R3-20）。
 *
 * 三段式（webui_arch P3 / supabase 调研 / design.md ADR-4）：
 *   onMutate → 乐观写入本地消息（即时回显 ≤16ms）
 *   mutationFn → chatWsClient.sendMessage
 *   onError → 回滚（移除乐观写入 + 错误提示 ≤100ms）
 *
 * 仅高频交互（聊天发送）用乐观更新；低频操作用失效刷新（蓝皮书 §四）。
 */
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { chatWsClient, type ChatImagePayload } from '@/lib/chat-ws-client'

import type { ChatMessage } from '../types'

/** 发送消息负载 */
export interface SendPayload {
  content: string
  images?: ChatImagePayload[]
  emojis?: string[]
  user_name: string
}

/** 乐观更新回调：由调用方（ChatPage）提供，操作本地消息列表 */
export interface OptimisticCallbacks {
  /** 乐观写入：把用户消息追加到本地列表（即时回显）→ 返回乐观消息用于回滚 */
  onOptimisticAdd: (message: ChatMessage) => void
  /** 回滚：移除指定乐观消息 id */
  onRollback: (optimisticId: string) => void
}

/**
 * 聊天消息发送乐观更新 hook。
 *
 * @param sessionId 会话 id
 * @param callbacks 乐观更新回调（操作本地消息列表）
 * @returns sendMessage / isPending / error
 */
export function useOptimisticSend(sessionId: string, callbacks: OptimisticCallbacks) {
  const mutation = useMutation({
    mutationFn: async (payload: SendPayload) => {
      // chatWsClient.sendMessage(sessionId, content, userName, options)
      return chatWsClient.sendMessage(
        sessionId,
        payload.content,
        payload.user_name,
        { images: payload.images }
      )
    },
    onMutate: async (payload: SendPayload) => {
      // 乐观写入本地消息（即时回显 ≤16ms——一帧内）
      const optimisticMessage: ChatMessage = {
        id: `optimistic_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        type: 'user',
        content: payload.content,
        timestamp: Date.now() / 1000,
        sender: { name: payload.user_name },
      }
      callbacks.onOptimisticAdd(optimisticMessage)
      return { optimisticId: optimisticMessage.id }
    },
    onError: (error, _variables, context) => {
      // 回滚（移除乐观写入 ≤100ms + 错误提示）
      if (context?.optimisticId) {
        callbacks.onRollback(context.optimisticId)
      }
      toast.error('消息发送失败', {
        description: error instanceof Error ? error.message : '请检查网络连接后重试',
      })
    },
  })

  return {
    sendMessage: (payload: SendPayload) => mutation.mutate(payload),
    isPending: mutation.isPending,
    error: mutation.error,
  }
}
