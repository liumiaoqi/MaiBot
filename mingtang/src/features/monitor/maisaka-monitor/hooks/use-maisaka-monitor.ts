/**
 * useMaisakaMonitor 领域 hook
 *
 * 管理 WebSocket 订阅引用计数 + 持续获取偏好 + 事件分发编排。
 * 模块级共享状态跨组件共享（design.md 决策 1）。
 *
 * 数据流：maisakaMonitorClient → handleMonitorEvent → event-handlers → monitorState → notifyStoreListeners → hook forceUpdate
 * 订阅状态机：idle → subscribing → active → deferring(200ms) → idle（StrictMode 竞态容忍）
 * 约束：consumer 卸载时若 bg=false 且无其他 consumer 则延迟退订；bg=true 时保持订阅
 */
import { useCallback, useEffect, useState } from 'react'

import { maisakaMonitorClient } from '@/lib/maisaka-monitor-client'
import type { MaisakaMonitorEvent } from '@/lib/maisaka-monitor-client'

import {
  appendTimelineEntry,
  updateSessionInfo,
  updateStageStatus,
  updateTimelineMessageContent,
} from './event-handlers'
import {
  BACKGROUND_COLLECTION_STORAGE_KEY,
  clearPersistedMonitorSnapshot,
  monitorState,
  notifyStoreListeners,
  resetPersistPending,
  schedulePersistMonitorSnapshot,
  schedulePersistUpdatedTimelineEntry,
  storeListeners,
  type SessionInfo,
  type StageStatusInfo,
  type TimelineEntry,
} from './persist-monitor'

// ─── hook 返回类型 ────────────────────────────────────────────

export interface UseMaisakaMonitorResult {
  /** 当前选中会话的时间线（已按 sessionId 过滤） */
  timeline: TimelineEntry[]
  /** 全部会话时间线（未过滤） */
  allTimeline: TimelineEntry[]
  /** 会话概要 Map（key=sessionId） */
  sessions: Map<string, SessionInfo>
  /** 阶段状态 Map（key=sessionId） */
  stageStatuses: Map<string, StageStatusInfo>
  /** 当前选中会话 ID */
  selectedSession: string | null
  /** 切换选中会话 */
  setSelectedSession: (sessionId: string | null) => void
  /** WebSocket 连接状态 */
  connected: boolean
  /** 持续获取开关 */
  backgroundCollection: boolean
  /** 切换持续获取（持久化至 localStorage） */
  setBackgroundCollectionEnabled: (enabled: boolean) => void
  /** 清空时间线 + IndexedDB 缓存 */
  clearTimeline: () => void
}

// ─── 模块级订阅状态 ───────────────────────────────────────────

let cachedConnected = false
let backgroundCollectionEnabled = false
let backgroundCollectionPreferenceLoaded = false
let activeConsumerCount = 0
let monitorSubscriptionStarted = false
let monitorSubscriptionPromise: Promise<void> | null = null
let monitorUnsubscribe: (() => Promise<void>) | null = null

// ─── 持续获取偏好 ─────────────────────────────────────────────

function loadBackgroundCollectionPreference(): boolean {
  if (backgroundCollectionPreferenceLoaded) {
    return backgroundCollectionEnabled
  }

  backgroundCollectionPreferenceLoaded = true
  if (typeof window !== 'undefined') {
    backgroundCollectionEnabled = window.localStorage.getItem(BACKGROUND_COLLECTION_STORAGE_KEY) === 'true'
  }
  return backgroundCollectionEnabled
}

function shouldKeepMonitorActive(): boolean {
  return activeConsumerCount > 0 || backgroundCollectionEnabled
}

// ─── 事件分发 ─────────────────────────────────────────────────

function handleMonitorEvent(event: MaisakaMonitorEvent): void {
  const dataRecord = event.data as unknown as Record<string, unknown>
  const sessionId = dataRecord.session_id as string
  const timestamp = dataRecord.timestamp as number

  if (event.type === 'stage.snapshot') {
    updateStageStatus(event)
    notifyStoreListeners()
    return
  }

  if (!sessionId || typeof timestamp !== 'number') {
    return
  }

  if (event.type === 'stage.status' || event.type === 'stage.removed') {
    updateStageStatus(event)
    updateSessionInfo(event, sessionId, timestamp)
    schedulePersistMonitorSnapshot(undefined, sessionId)
    notifyStoreListeners()
    return
  }

  if (event.type === 'message.updated') {
    const updatedEntryId = updateTimelineMessageContent(event, sessionId)
    updateSessionInfo(event, sessionId, timestamp)
    if (updatedEntryId) {
      schedulePersistUpdatedTimelineEntry(updatedEntryId, sessionId)
      notifyStoreListeners()
    }
    return
  }

  const entry: TimelineEntry = {
    id: `evt_${++monitorState.entryCounter}_${Date.now()}`,
    type: event.type,
    data: event.data,
    timestamp,
    sessionId,
  }
  appendTimelineEntry(entry)

  updateSessionInfo(event, sessionId, timestamp)

  if (monitorState.selectedSession === null) {
    monitorState.selectedSession = sessionId
  }

  schedulePersistMonitorSnapshot(entry, sessionId)
  notifyStoreListeners()
}

// ─── 订阅管理 ─────────────────────────────────────────────────

function ensureMonitorSubscription(): void {
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

function stopMonitorSubscriptionIfIdle(): void {
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

// ─── hook ─────────────────────────────────────────────────────

export function useMaisakaMonitor(): UseMaisakaMonitorResult {
  const [timeline, setTimeline] = useState<TimelineEntry[]>(monitorState.timeline)
  const [sessions, setSessions] = useState(() => new Map(monitorState.sessions))
  const [stageStatuses, setStageStatuses] = useState(() => new Map(monitorState.stageStatuses))
  const [selectedSession, setSelectedSessionState] = useState<string | null>(monitorState.selectedSession)
  const [connected, setConnected] = useState(cachedConnected)
  const [backgroundCollection, setBackgroundCollection] = useState(loadBackgroundCollectionPreference)

  useEffect(() => {
    activeConsumerCount += 1
    ensureMonitorSubscription()
    const syncFromStore = () => {
      setTimeline(monitorState.timeline)
      setSessions(new Map(monitorState.sessions))
      setStageStatuses(new Map(monitorState.stageStatuses))
      setSelectedSessionState(monitorState.selectedSession)
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
    monitorState.timeline = []
    monitorState.sessions = new Map()
    monitorState.stageStatuses = new Map()
    monitorState.selectedSession = null
    setTimeline([])
    setSessions(new Map())
    setStageStatuses(new Map())
    setSelectedSessionState(null)
    resetPersistPending()
    void clearPersistedMonitorSnapshot()
    notifyStoreListeners()
  }, [])

  const setSelectedSession = useCallback((sessionId: string | null) => {
    monitorState.selectedSession = sessionId
    setSelectedSessionState(sessionId)
    schedulePersistMonitorSnapshot()
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
    stageStatuses,
    selectedSession,
    setSelectedSession,
    connected,
    backgroundCollection,
    setBackgroundCollectionEnabled,
    clearTimeline,
  }
}