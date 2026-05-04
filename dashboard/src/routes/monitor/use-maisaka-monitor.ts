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
  isGroupChat?: boolean
  groupId?: string | null
  userId?: string | null
  platform?: string
  lastActivity: number
  eventCount: number
}

/** 最大保留的时间线条目数 */
const MAX_TIMELINE_ENTRIES = 500

function resolveSessionDisplayName({
  fallbackName,
  groupId,
  isGroupChat,
  sessionId,
  userId,
}: {
  fallbackName?: string
  groupId?: string | null
  isGroupChat?: boolean
  sessionId: string
  userId?: string | null
}) {
  const targetId = isGroupChat ? groupId : userId
  const normalizedName = fallbackName?.trim()

  if (targetId && normalizedName?.endsWith(`(${targetId})`)) {
    return normalizedName
  }
  if (normalizedName && targetId && normalizedName !== targetId && normalizedName !== sessionId) {
    return `${normalizedName}(${targetId})`
  }
  if (isGroupChat && groupId) {
    return groupId
  }
  if (!isGroupChat && userId) {
    return userId
  }
  return fallbackName || sessionId.slice(0, 8)
}

let entryCounter = 0
let cachedTimeline: TimelineEntry[] = []
let cachedSessions: Map<string, SessionInfo> = new Map()
let cachedSelectedSession: string | null = null

export function useMaisakaMonitor() {
  const [timeline, setTimeline] = useState<TimelineEntry[]>(cachedTimeline)
  const [sessions, setSessions] = useState<Map<string, SessionInfo>>(new Map(cachedSessions))
  const [selectedSession, setSelectedSessionState] = useState<string | null>(cachedSelectedSession)
  const [connected, setConnected] = useState(false)
  const unsubRef = useRef<(() => Promise<void>) | null>(null)

  const handleEvent = useCallback((event: MaisakaMonitorEvent) => {
    const dataRecord = event.data as unknown as Record<string, unknown>
    const sessionId = dataRecord.session_id as string
    const timestamp = dataRecord.timestamp as number
    const isGroupChat = typeof dataRecord.is_group_chat === 'boolean'
      ? dataRecord.is_group_chat
      : undefined
    const groupId = typeof dataRecord.group_id === 'string' ? dataRecord.group_id : null
    const userId = typeof dataRecord.user_id === 'string' ? dataRecord.user_id : null
    const platform = typeof dataRecord.platform === 'string' ? dataRecord.platform : undefined
    const sessionName = typeof dataRecord.session_name === 'string'
      ? dataRecord.session_name
      : undefined

    const entry: TimelineEntry = {
      id: `evt_${++entryCounter}_${Date.now()}`,
      type: event.type,
      data: event.data,
      timestamp,
      sessionId,
    }

    setTimeline((prev) => {
      const next = [...prev, entry]
      const trimmed = next.length > MAX_TIMELINE_ENTRIES
        ? next.slice(next.length - MAX_TIMELINE_ENTRIES)
        : next
      cachedTimeline = trimmed
      return trimmed
    })

    // 更新会话信息
    if (event.type === 'session.start') {
      setSessions((prev) => {
        const next = new Map(prev)
        next.set(sessionId, {
          sessionId,
          sessionName: resolveSessionDisplayName({
            fallbackName: sessionName,
            groupId,
            isGroupChat,
            sessionId,
            userId,
          }),
          isGroupChat,
          groupId,
          userId,
          platform,
          lastActivity: timestamp,
          eventCount: (prev.get(sessionId)?.eventCount ?? 0) + 1,
        })
        cachedSessions = next
        return next
      })
    } else {
      setSessions((prev) => {
        const existing = prev.get(sessionId)
        if (!existing) {
          const next = new Map(prev)
          next.set(sessionId, {
            sessionId,
            sessionName: resolveSessionDisplayName({
              fallbackName: sessionName,
              groupId,
              isGroupChat,
              sessionId,
              userId,
            }),
            isGroupChat,
            groupId,
            userId,
            platform,
            lastActivity: timestamp,
            eventCount: 1,
          })
          cachedSessions = next
          return next
        }
        const next = new Map(prev)
        next.set(sessionId, {
          ...existing,
          sessionName: resolveSessionDisplayName({
            fallbackName: sessionName ?? existing.sessionName,
            groupId: groupId ?? existing.groupId,
            isGroupChat: isGroupChat ?? existing.isGroupChat,
            sessionId,
            userId: userId ?? existing.userId,
          }),
          isGroupChat: isGroupChat ?? existing.isGroupChat,
          groupId: groupId ?? existing.groupId,
          userId: userId ?? existing.userId,
          platform: platform ?? existing.platform,
          lastActivity: timestamp,
          eventCount: existing.eventCount + 1,
        })
        cachedSessions = next
        return next
      })
    }

    // 自动选中第一个会话
    setSelectedSessionState((current) => {
      const next = current ?? sessionId
      cachedSelectedSession = next
      return next
    })
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
    cachedTimeline = []
    setTimeline([])
  }, [])

  const setSelectedSession = useCallback((sessionId: string | null) => {
    cachedSelectedSession = sessionId
    setSelectedSessionState(sessionId)
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
