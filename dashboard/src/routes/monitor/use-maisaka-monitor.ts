/**
 * MaiSaka 聊天流实时监控 - React Hook
 *
 * 管理 WebSocket 订阅与事件流的状态。
 */
import { useCallback, useEffect, useState } from 'react'

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
const BACKGROUND_COLLECTION_STORAGE_KEY = 'maisaka-monitor-background-collection'

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
let cachedConnected = false
let backgroundCollectionEnabled = false
let backgroundCollectionPreferenceLoaded = false
let activeConsumerCount = 0
let monitorSubscriptionStarted = false
let monitorSubscriptionPromise: Promise<void> | null = null
let monitorUnsubscribe: (() => Promise<void>) | null = null
const storeListeners = new Set<() => void>()

function notifyStoreListeners() {
  storeListeners.forEach((listener) => listener())
}

function loadBackgroundCollectionPreference() {
  if (backgroundCollectionPreferenceLoaded) {
    return backgroundCollectionEnabled
  }

  backgroundCollectionPreferenceLoaded = true
  if (typeof window !== 'undefined') {
    backgroundCollectionEnabled = window.localStorage.getItem(BACKGROUND_COLLECTION_STORAGE_KEY) === 'true'
  }
  return backgroundCollectionEnabled
}

function shouldKeepMonitorActive() {
  return activeConsumerCount > 0 || backgroundCollectionEnabled
}

function appendTimelineEntry(entry: TimelineEntry) {
  const next = [...cachedTimeline, entry]
  cachedTimeline = next.length > MAX_TIMELINE_ENTRIES
    ? next.slice(next.length - MAX_TIMELINE_ENTRIES)
    : next
}

function updateSessionInfo(event: MaisakaMonitorEvent, sessionId: string, timestamp: number) {
  const dataRecord = event.data as unknown as Record<string, unknown>
  const isGroupChat = typeof dataRecord.is_group_chat === 'boolean'
    ? dataRecord.is_group_chat
    : undefined
  const groupId = typeof dataRecord.group_id === 'string' ? dataRecord.group_id : null
  const userId = typeof dataRecord.user_id === 'string' ? dataRecord.user_id : null
  const platform = typeof dataRecord.platform === 'string' ? dataRecord.platform : undefined
  const sessionName = typeof dataRecord.session_name === 'string'
    ? dataRecord.session_name
    : undefined

  const next = new Map(cachedSessions)
  const existing = next.get(sessionId)

  if (event.type === 'session.start' || !existing) {
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
      eventCount: (existing?.eventCount ?? 0) + 1,
    })
  } else {
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
  }

  cachedSessions = next
}

function handleMonitorEvent(event: MaisakaMonitorEvent) {
  const dataRecord = event.data as unknown as Record<string, unknown>
  const sessionId = dataRecord.session_id as string
  const timestamp = dataRecord.timestamp as number

  if (!sessionId || typeof timestamp !== 'number') {
    return
  }

  appendTimelineEntry({
    id: `evt_${++entryCounter}_${Date.now()}`,
    type: event.type,
    data: event.data,
    timestamp,
    sessionId,
  })

  updateSessionInfo(event, sessionId, timestamp)

  if (cachedSelectedSession === null) {
    cachedSelectedSession = sessionId
  }

  notifyStoreListeners()
}

function ensureMonitorSubscription() {
  if (monitorSubscriptionStarted || monitorSubscriptionPromise !== null) {
    return
  }

  monitorSubscriptionPromise = maisakaMonitorClient
    .subscribe(handleMonitorEvent)
    .then((unsub) => {
      monitorUnsubscribe = unsub
      if (!shouldKeepMonitorActive()) {
        monitorUnsubscribe = null
        void unsub()
        cachedConnected = false
        notifyStoreListeners()
        return
      }
      monitorSubscriptionStarted = true
      cachedConnected = true
      notifyStoreListeners()
    })
    .catch((error) => {
      console.error('MaiSaka 监控订阅失败:', error)
      cachedConnected = false
      notifyStoreListeners()
    })
    .finally(() => {
      monitorSubscriptionPromise = null
    })
}

function stopMonitorSubscriptionIfIdle() {
  if (shouldKeepMonitorActive()) {
    return
  }

  if (monitorUnsubscribe) {
    const unsub = monitorUnsubscribe
    monitorUnsubscribe = null
    monitorSubscriptionStarted = false
    cachedConnected = false
    notifyStoreListeners()
    void unsub()
  }
}

export function useMaisakaMonitor() {
  const [timeline, setTimeline] = useState<TimelineEntry[]>(cachedTimeline)
  const [sessions, setSessions] = useState<Map<string, SessionInfo>>(new Map(cachedSessions))
  const [selectedSession, setSelectedSessionState] = useState<string | null>(cachedSelectedSession)
  const [connected, setConnected] = useState(cachedConnected)
  const [backgroundCollection, setBackgroundCollection] = useState(loadBackgroundCollectionPreference)

  useEffect(() => {
    activeConsumerCount += 1
    ensureMonitorSubscription()
    const syncFromStore = () => {
      setTimeline(cachedTimeline)
      setSessions(new Map(cachedSessions))
      setSelectedSessionState(cachedSelectedSession)
      setConnected(cachedConnected)
      setBackgroundCollection(backgroundCollectionEnabled)
    }

    storeListeners.add(syncFromStore)
    syncFromStore()
    return () => {
      storeListeners.delete(syncFromStore)
      activeConsumerCount = Math.max(0, activeConsumerCount - 1)
      stopMonitorSubscriptionIfIdle()
    }
  }, [])

  const clearTimeline = useCallback(() => {
    cachedTimeline = []
    setTimeline([])
    notifyStoreListeners()
  }, [])

  const setSelectedSession = useCallback((sessionId: string | null) => {
    cachedSelectedSession = sessionId
    setSelectedSessionState(sessionId)
    notifyStoreListeners()
  }, [])

  const setBackgroundCollectionEnabled = useCallback((enabled: boolean) => {
    backgroundCollectionEnabled = enabled
    backgroundCollectionPreferenceLoaded = true
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(BACKGROUND_COLLECTION_STORAGE_KEY, String(enabled))
    }

    if (enabled) {
      ensureMonitorSubscription()
    } else {
      stopMonitorSubscriptionIfIdle()
    }
    notifyStoreListeners()
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
    backgroundCollection,
    setBackgroundCollectionEnabled,
    clearTimeline,
  }
}
