/**
 * MaiSaka 监控持久化模块（数据层）
 *
 * 定义前端视图模型类型 + IndexedDB schema + 持久化模块函数。
 * 模块级共享状态跨组件共享（design.md 决策 1：状态归属选模块级共享）。
 * IndexedDB 不可用时降级为纯内存模式（spec §4.2 #4）。
 *
 * 数据流：use-maisaka-monitor.ts → persist-monitor.ts → IndexedDB
 * 约束：所有 IndexedDB 操作 try/catch + console.warn，不抛错阻断页面
 */
import { openDB, type DBSchema, type IDBPDatabase } from 'idb'

import type { MaisakaMonitorEvent } from '@/lib/maisaka-monitor-client'

// ─── 视图模型类型 ─────────────────────────────────────────────

/** 单条时间线事件（前端视图模型） */
export interface TimelineEntry {
  /** 唯一 ID，格式 evt_${++counter}_${Date.now()} */
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

/** 阶段状态信息（updatedAt 用于新旧比较——旧不覆盖新） */
export interface StageStatusInfo {
  sessionId: string
  sessionName?: string
  stage: string
  detail: string
  roundText: string
  agentState: string
  stageStartedAt: number
  updatedAt: number
}

/** 统计信息（由 timeline 聚合） */
export interface MonitorStats {
  messages: number
  cycles: number
  toolCalls: number
}

// ─── 持久化类型 ───────────────────────────────────────────────

export interface PersistedTimelineEntry extends TimelineEntry {
  persistedAt: number
}

export interface MonitorMetaRecord {
  key: string
  value: unknown
}

export interface MaisakaMonitorDb extends DBSchema {
  timeline: {
    key: string
    value: PersistedTimelineEntry
    indexes: {
      'by-timestamp': number
    }
  }
  sessions: {
    key: string
    value: SessionInfo
  }
  meta: {
    key: string
    value: MonitorMetaRecord
  }
}

// ─── 常量 ─────────────────────────────────────────────────────

/** 内存中最多展示的时间线条目数 */
export const MAX_TIMELINE_ENTRIES = 3000
/** IndexedDB 中最多持久化的时间线条目数 */
export const MAX_PERSISTED_TIMELINE_ENTRIES = 10000
/** 每累积 N 条触发一次 prune */
export const PERSIST_PRUNE_INTERVAL = 200
/** 持续获取偏好的 localStorage 键 */
export const BACKGROUND_COLLECTION_STORAGE_KEY = 'maisaka-monitor-background-collection'
/** IndexedDB 库名 */
export const MONITOR_DB_NAME = 'maisaka-monitor-db'
/** IndexedDB 库版本 */
export const MONITOR_DB_VERSION = 1
/** 持久化节流延迟（ms） */
export const PERSIST_THROTTLE_MS = 300

// ─── 模块级共享状态（跨组件共享——对象包装避免 export let live binding 陷阱） ──

export const monitorState = {
  timeline: [] as TimelineEntry[],
  sessions: new Map<string, SessionInfo>(),
  stageStatuses: new Map<string, StageStatusInfo>(),
  selectedSession: null as string | null,
  entryCounter: 0,
}

/** store 监听器集合（hook 注册 forceUpdate） */
export const storeListeners = new Set<() => void>()

// ─── 模块级持久化内部状态 ─────────────────────────────────────

let persistSnapshotTimer: ReturnType<typeof setTimeout> | null = null
let monitorDbPromise: Promise<IDBPDatabase<MaisakaMonitorDb>> | null = null
let persistedEntryCountSincePrune = 0
let pendingPersistEntries: TimelineEntry[] = []
let pendingPersistUpdatedEntryIds = new Set<string>()
let pendingPersistSessionIds = new Set<string>()
let pendingPersistMeta = false

// ─── 辅助函数 ─────────────────────────────────────────────────

/** 通知所有 store 监听器（hook forceUpdate） */
export function notifyStoreListeners(): void {
  storeListeners.forEach((listener) => listener())
}

/** 从持久化记录还原为 TimelineEntry（剥离 persistedAt） */
function toTimelineEntry(entry: PersistedTimelineEntry): TimelineEntry {
  return {
    id: entry.id,
    type: entry.type,
    data: entry.data,
    timestamp: entry.timestamp,
    sessionId: entry.sessionId,
  }
}

/** 从原始事件数据构造 StageStatusInfo（字段校验——缺 session_id 返回 null） */
export function toStageStatusInfo(raw: Record<string, unknown>): StageStatusInfo | null {
  const sessionId = typeof raw.session_id === 'string' ? raw.session_id : ''
  if (!sessionId) {
    return null
  }
  return {
    sessionId,
    sessionName: typeof raw.session_name === 'string' ? raw.session_name : undefined,
    stage: typeof raw.stage === 'string' ? raw.stage : '',
    detail: typeof raw.detail === 'string' ? raw.detail : '',
    roundText: typeof raw.round_text === 'string' ? raw.round_text : '',
    agentState: typeof raw.agent_state === 'string' ? raw.agent_state : '',
    stageStartedAt: typeof raw.stage_started_at === 'number' ? raw.stage_started_at : Date.now() / 1000,
    updatedAt: typeof raw.updated_at === 'number' ? raw.updated_at : Date.now() / 1000,
  }
}

// ─── IndexedDB 持久化函数 ─────────────────────────────────────

/** 获取 IndexedDB 实例（不可用时返回 null——降级内存模式） */
export function getMonitorDb(): Promise<IDBPDatabase<MaisakaMonitorDb>> | null {
  if (typeof window === 'undefined' || !window.indexedDB) {
    return null
  }

  monitorDbPromise ??= openDB<MaisakaMonitorDb>(MONITOR_DB_NAME, MONITOR_DB_VERSION, {
    upgrade(db) {
      const timelineStore = db.createObjectStore('timeline', { keyPath: 'id' })
      timelineStore.createIndex('by-timestamp', 'timestamp')
      db.createObjectStore('sessions', { keyPath: 'sessionId' })
      db.createObjectStore('meta', { keyPath: 'key' })
    },
  })

  return monitorDbPromise
}

/** 从 IndexedDB 异步恢复历史快照（不阻塞首屏——恢复前 cachedTimeline=[]） */
export async function loadMonitorSnapshot(): Promise<void> {
  if (typeof window === 'undefined') {
    return
  }

  try {
    const dbPromise = getMonitorDb()
    if (!dbPromise) {
      return
    }

    const db = await dbPromise
    const [timelineRecords, sessionRecords, selectedSessionMeta, entryCounterMeta] = await Promise.all([
      db.getAllFromIndex('timeline', 'by-timestamp'),
      db.getAll('sessions'),
      db.get('meta', 'selectedSession'),
      db.get('meta', 'entryCounter'),
    ])

    monitorState.timeline = timelineRecords
      .slice(-MAX_TIMELINE_ENTRIES)
      .map(toTimelineEntry)
    monitorState.sessions = new Map(sessionRecords.map((session) => [session.sessionId, session]))
    monitorState.selectedSession = typeof selectedSessionMeta?.value === 'string' ? selectedSessionMeta.value : null
    monitorState.entryCounter = typeof entryCounterMeta?.value === 'number' ? entryCounterMeta.value : monitorState.timeline.length
    notifyStoreListeners()
  } catch (error) {
    console.warn('读取 MaiSaka 观察 IndexedDB 缓存失败，已忽略:', error)
  }
}

/** 删除最旧的持久化时间线条目，保留 MAX_PERSISTED_TIMELINE_ENTRIES 上限 */
async function prunePersistedTimeline(db: IDBPDatabase<MaisakaMonitorDb>): Promise<void> {
  const keys = await db.getAllKeysFromIndex('timeline', 'by-timestamp')
  const overflowCount = keys.length - MAX_PERSISTED_TIMELINE_ENTRIES
  if (overflowCount <= 0) {
    return
  }

  const tx = db.transaction('timeline', 'readwrite')
  for (const key of keys.slice(0, overflowCount)) {
    await tx.store.delete(key)
  }
  await tx.done
}

/** 单事务批量写入所有 pending entries/sessions/meta（节流 300ms 后触发） */
export async function flushMonitorSnapshot(): Promise<void> {
  try {
    const dbPromise = getMonitorDb()
    if (!dbPromise) {
      return
    }

    const entries = pendingPersistEntries
    const updatedEntryIds = Array.from(pendingPersistUpdatedEntryIds)
    const sessionIds = Array.from(pendingPersistSessionIds)
    const shouldPersistMeta = pendingPersistMeta
    pendingPersistEntries = []
    pendingPersistUpdatedEntryIds = new Set()
    pendingPersistSessionIds = new Set()
    pendingPersistMeta = false

    if (entries.length === 0 && updatedEntryIds.length === 0 && sessionIds.length === 0 && !shouldPersistMeta) {
      return
    }

    const db = await dbPromise
    const tx = db.transaction(['timeline', 'sessions', 'meta'], 'readwrite')
    const persistedAt = Date.now()
    for (const entry of entries) {
      await tx.objectStore('timeline').put({ ...entry, persistedAt })
    }
    for (const entryId of updatedEntryIds) {
      const entry = monitorState.timeline.find((item) => item.id === entryId)
      if (entry) {
        await tx.objectStore('timeline').put({ ...entry, persistedAt })
      }
    }
    for (const sessionId of sessionIds) {
      const session = monitorState.sessions.get(sessionId)
      if (session) {
        await tx.objectStore('sessions').put(session)
      }
    }
    await tx.objectStore('meta').put({ key: 'selectedSession', value: monitorState.selectedSession })
    await tx.objectStore('meta').put({ key: 'entryCounter', value: monitorState.entryCounter })
    await tx.done

    persistedEntryCountSincePrune += entries.length
    if (persistedEntryCountSincePrune >= PERSIST_PRUNE_INTERVAL) {
      persistedEntryCountSincePrune = 0
      await prunePersistedTimeline(db)
    }
  } catch (error) {
    console.warn('保存 MaiSaka 观察 IndexedDB 缓存失败，已忽略:', error)
  }
}

/** 清空 IndexedDB 中 timeline/sessions/meta 三 store */
export async function clearPersistedMonitorSnapshot(): Promise<void> {
  try {
    const dbPromise = getMonitorDb()
    if (!dbPromise) {
      return
    }
    const db = await dbPromise
    const tx = db.transaction(['timeline', 'sessions', 'meta'], 'readwrite')
    await Promise.all([
      tx.objectStore('timeline').clear(),
      tx.objectStore('sessions').clear(),
      tx.objectStore('meta').clear(),
    ])
    await tx.done
  } catch (error) {
    console.warn('清空 MaiSaka 观察 IndexedDB 缓存失败，已忽略:', error)
  }
}

/** 调度持久化快照写入（节流 300ms——合并短时间多次事件为一次批量写入） */
export function schedulePersistMonitorSnapshot(entry?: TimelineEntry, sessionId?: string): void {
  if (typeof window === 'undefined') {
    return
  }
  if (entry) {
    pendingPersistEntries.push(entry)
  }
  if (sessionId) {
    pendingPersistSessionIds.add(sessionId)
  }
  pendingPersistMeta = true
  if (persistSnapshotTimer !== null) {
    window.clearTimeout(persistSnapshotTimer)
  }
  persistSnapshotTimer = window.setTimeout(() => {
    persistSnapshotTimer = null
    void flushMonitorSnapshot()
  }, PERSIST_THROTTLE_MS)
}

/** 调度已更新条目的持久化（message.updated 按 message_id 匹配更新而非新增） */
export function schedulePersistUpdatedTimelineEntry(entryId: string, sessionId?: string): void {
  if (typeof window === 'undefined') {
    return
  }
  pendingPersistUpdatedEntryIds.add(entryId)
  if (sessionId) {
    pendingPersistSessionIds.add(sessionId)
  }
  pendingPersistMeta = true
  if (persistSnapshotTimer !== null) {
    window.clearTimeout(persistSnapshotTimer)
  }
  persistSnapshotTimer = window.setTimeout(() => {
    persistSnapshotTimer = null
    void flushMonitorSnapshot()
  }, PERSIST_THROTTLE_MS)
}

/** 重置持久化 pending 状态（clearTimeline 调用——避免 flush 写入已清空的数据） */
export function resetPersistPending(): void {
  pendingPersistEntries = []
  pendingPersistUpdatedEntryIds = new Set()
  pendingPersistSessionIds = new Set()
  pendingPersistMeta = false
  if (persistSnapshotTimer !== null) {
    clearTimeout(persistSnapshotTimer)
    persistSnapshotTimer = null
  }
}

// ─── 模块加载时异步恢复历史（不阻塞首屏） ─────────────────────

void loadMonitorSnapshot()