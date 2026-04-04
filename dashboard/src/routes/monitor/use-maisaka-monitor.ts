/**
 * MaiSaka 聊天流实时监控 - React Hook
 *
 * 管理 WebSocket 订阅与事件流的状态。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import type { MaisakaMonitorEvent } from '@/lib/maisaka-monitor-client'
import { maisakaMonitorClient } from '@/lib/maisaka-monitor-client'

/** 单条时间线事件（前端视图模型） */
export interface TimelineEntry {
  /** 唯一 ID */
  id: string
  /** 事件类型 */
  type: MaisakaMonitorEvent['type']
  /** 原始事件数据 */
  data: MaisakaMonitorEvent['data']
  /** 事件时间戳 */
  timestamp: number
  /** 所属会话 ID */
  sessionId: string
}

/** 会话概要信息 */
export interface SessionInfo {
  sessionId: string
  sessionName: string
  lastActivity: number
  eventCount: number
}

/** 最大保留的时间线条目数 */
const MAX_TIMELINE_ENTRIES = 500

let entryCounter = 0

export function useMaisakaMonitor() {
  const [timeline, setTimeline] = useState<TimelineEntry[]>([])
  const [sessions, setSessions] = useState<Map<string, SessionInfo>>(new Map())
  const [selectedSession, setSelectedSession] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const unsubRef = useRef<(() => Promise<void>) | null>(null)

  const handleEvent = useCallback((event: MaisakaMonitorEvent) => {
    const sessionId = (event.data as unknown as Record<string, unknown>).session_id as string
    const timestamp = (event.data as unknown as Record<string, unknown>).timestamp as number

    const entry: TimelineEntry = {
      id: `evt_${++entryCounter}_${Date.now()}`,
      type: event.type,
      data: event.data,
      timestamp,
      sessionId,
    }

    setTimeline((prev) => {
      const next = [...prev, entry]
      return next.length > MAX_TIMELINE_ENTRIES
        ? next.slice(next.length - MAX_TIMELINE_ENTRIES)
        : next
    })

    // 更新会话信息
    if (event.type === 'session.start') {
      const d = event.data
      setSessions((prev) => {
        const next = new Map(prev)
        next.set(sessionId, {
          sessionId,
          sessionName: d.session_name,
          lastActivity: timestamp,
          eventCount: (prev.get(sessionId)?.eventCount ?? 0) + 1,
        })
        return next
      })
    } else {
      setSessions((prev) => {
        const existing = prev.get(sessionId)
        if (!existing) {
          const next = new Map(prev)
          next.set(sessionId, {
            sessionId,
            sessionName: sessionId.slice(0, 8),
            lastActivity: timestamp,
            eventCount: 1,
          })
          return next
        }
        const next = new Map(prev)
        next.set(sessionId, {
          ...existing,
          lastActivity: timestamp,
          eventCount: existing.eventCount + 1,
        })
        return next
      })
    }

    // 自动选中第一个会话
    setSelectedSession((current) => current ?? sessionId)
  }, [])

  useEffect(() => {
    let cancelled = false

    maisakaMonitorClient.subscribe(handleEvent).then((unsub) => {
      if (cancelled) {
        void unsub()
        return
      }
      unsubRef.current = unsub
      setConnected(true)
    })

    return () => {
      cancelled = true
      if (unsubRef.current) {
        void unsubRef.current()
        unsubRef.current = null
      }
      setConnected(false)
    }
  }, [handleEvent])

  const clearTimeline = useCallback(() => {
    setTimeline([])
  }, [])

  /** 当前选中会话的时间线 */
  const filteredTimeline = selectedSession
    ? timeline.filter((e) => e.sessionId === selectedSession)
    : timeline

  return {
    timeline: filteredTimeline,
    allTimeline: timeline,
    sessions,
    selectedSession,
    setSelectedSession,
    connected,
    clearTimeline,
  }
}
