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
    void fetchResources()

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

    if (unifiedWsClient.getStatus() === 'connected') {
      setIsConnected(true)
      void unifiedWsClient.subscribe('system_resources', 'main').catch(() => {
        startPolling()
      })
    } else {
      startPolling()
    }

    return () => {
      mountedRef.current = false
      removeEventListener()
      removeConnectionListener()
      stopPolling()
      void unifiedWsClient.unsubscribe('system_resources', 'main').catch(() => {})
    }
  }, [fetchResources, startPolling, stopPolling])

  return { data, isConnected, error, refetch: fetchResources }
}