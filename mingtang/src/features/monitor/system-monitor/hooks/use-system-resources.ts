/**
 * useSystemResources 系统资源 hook（T1-6-5 搬移——React 19 适配）
 *
 * React 19 适配（design.md §2.1.3 D）：
 * - 模式 4：ws 订阅/退订在 effect 内做（useEffect 仅副作用不 setState）
 * - 模式 5：effect 内不直接调含同步 setState 的逻辑（初始连接状态判断 setIsConnected）
 *   ——用 setTimeout(0) + cleanup 调度初始化
 * - 数据更新通过回调 setState（ws 事件回调 / async await 后）
 * - ws 断开保留最后一次数据 + 轮询兜底（spec.md §5.3.9 异常场景 2）
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { getSystemResources, type SystemResources } from '@/lib/system-api'
import { unifiedWsClient, type WsEventEnvelope } from '@/lib/unified-ws'

const POLL_INTERVAL_MS = 30_000

export function useSystemResources() {
  const [data, setData] = useState<SystemResources | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const pollTimerRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  const fetchResources = useCallback(async () => {
    try {
      const result = await getSystemResources()
      if (mountedRef.current) {
        setData(result)
        setError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err : new Error(String(err)))
      }
    }
  }, [])

  const startPolling = useCallback(() => {
    if (pollTimerRef.current !== null) return
    pollTimerRef.current = window.setInterval(() => {
      void fetchResources()
    }, POLL_INTERVAL_MS)
  }, [fetchResources])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    // 模式 5：初始加载 + 连接状态同步 setState（setIsConnected）用 setTimeout(0) 调度
    const initTimer = window.setTimeout(() => {
      void fetchResources()
      if (unifiedWsClient.getStatus() === 'connected') {
        setIsConnected(true)
        void unifiedWsClient.subscribe('system_resources', 'main').catch(() => {
          startPolling()
        })
      } else {
        startPolling()
      }
    }, 0)

    const handleEvent = (message: WsEventEnvelope) => {
      if (message.domain === 'system_resources' && (message.event === 'update' || message.event === 'snapshot')) {
        const payload = message.data as unknown as SystemResources
        setData(payload)
        setError(null)
      }
    }

    const handleConnectionChange = (connected: boolean) => {
      setIsConnected(connected)
      if (connected) {
        stopPolling()
        void unifiedWsClient.subscribe('system_resources', 'main').catch(() => {
          startPolling()
        })
      } else {
        startPolling()
      }
    }

    const removeEventListener = unifiedWsClient.addEventListener(handleEvent)
    const removeConnectionListener = unifiedWsClient.onConnectionChange(handleConnectionChange)

    return () => {
      mountedRef.current = false
      window.clearTimeout(initTimer)
      removeEventListener()
      removeConnectionListener()
      stopPolling()
      void unifiedWsClient.unsubscribe('system_resources', 'main').catch(() => {})
    }
  }, [fetchResources, startPolling, stopPolling])

  return { data, isConnected, error, refetch: fetchResources }
}