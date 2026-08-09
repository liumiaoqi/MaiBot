/**
 * useRuntimeStatus 运行状态订阅 hook（R3-1-5）
 *
 * 订阅 maisaka-monitor-client 5 种事件（stage.snapshot/status/removed + llm.retry/error——
 * 16 种中子集），用 resolveStatusKind 按 stage 关键词推断 thinking/typing/acting/error，
 * matchesMonitorTarget 三级匹配 tab。
 *
 * 退订 200ms 延迟防 StrictMode 竞态由 lib 已实现（maisakaMonitorClient.subscribe 内部）。
 *
 * 核心职责（REQ-R3-04 / REQ-R3-19）：运行状态实时推断 + 跨组件消费。
 */
import { useEffect, useState } from 'react'

import { maisakaMonitorClient } from '@/lib/maisaka-monitor-client'

import type { ChatRuntimeStatus, ChatTab, MonitorTargetCandidate } from '../types'
import { matchesMonitorTarget, resolveStatusKind } from '../utils'

interface UseRuntimeStatusResult {
  status: ChatRuntimeStatus
}

/**
 * 订阅运行状态事件，推断当前 tab 的运行状态。
 *
 * @param tab 当前活跃聊天标签（undefined 时返回 idle）
 * @returns { status } 运行状态种类
 */
export function useRuntimeStatus(tab: ChatTab | undefined): UseRuntimeStatusResult {
  const [internalStatus, setInternalStatus] = useState<ChatRuntimeStatus>('idle')

  useEffect(() => {
    if (!tab) {
      return
    }

    let cancelled = false

    const handleEvent = (event: { type: string; data: Record<string, unknown> }) => {
      if (cancelled) return

      switch (event.type) {
        case 'stage.status': {
          const data = event.data as MonitorTargetCandidate & {
            stage?: string
            detail?: string
          }
          if (matchesMonitorTarget(data, tab)) {
            setInternalStatus(resolveStatusKind(data.stage ?? '', data.detail ?? ''))
          }
          break
        }
        case 'stage.snapshot': {
          const data = event.data as {
            entries?: Array<MonitorTargetCandidate & { stage?: string; detail?: string }>
          }
          const entries = data.entries ?? []
          // 找匹配 tab 的 entry，取最后一个的状态
          for (let i = entries.length - 1; i >= 0; i--) {
            const entry = entries[i]
            if (matchesMonitorTarget(entry, tab)) {
              setInternalStatus(resolveStatusKind(entry.stage ?? '', entry.detail ?? ''))
              break
            }
          }
          break
        }
        case 'stage.removed': {
          const data = event.data as MonitorTargetCandidate
          if (matchesMonitorTarget(data, tab)) {
            setInternalStatus('idle')
          }
          break
        }
        case 'llm.error':
        case 'llm.retry': {
          const data = event.data as MonitorTargetCandidate
          if (matchesMonitorTarget(data, tab)) {
            setInternalStatus('error')
          }
          break
        }
      }
    }

    // subscribe 返回 Promise<unsubscribe>——异步订阅
    let unsubscribe: (() => Promise<void>) | null = null
    void maisakaMonitorClient.subscribe(handleEvent as never).then((fn) => {
      if (cancelled) {
        void fn()
      } else {
        unsubscribe = fn
      }
    })

    return () => {
      cancelled = true
      if (unsubscribe) {
        void unsubscribe()
      }
    }
    // 依赖 tab?.id 而非 tab 对象——避免每次 render 新对象导致 effect 重执行
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab?.id])

  // 派生状态：tab 为 undefined 时返回 idle（不在 effect 里 setState）
  const status: ChatRuntimeStatus = tab ? internalStatus : 'idle'
  return { status }
}

