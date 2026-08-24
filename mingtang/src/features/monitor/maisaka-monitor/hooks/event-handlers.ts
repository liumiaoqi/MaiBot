/**
 * MaiSaka 监控事件处理纯函数
 *
 * 处理 8 种事件类型的状态更新逻辑，操作 monitorState 中的共享状态。
 * 不涉及持久化副作用——persist 调用由 use-maisaka-monitor.ts 的 handleMonitorEvent 编排。
 *
 * 事件类型：session.start / stage.status / stage.removed / stage.snapshot /
 *           message.ingested / message.sent / message.updated / planner.finalized
 */
import type { MaisakaMonitorEvent } from '@/lib/maisaka-monitor-client'

import {
  MAX_TIMELINE_ENTRIES,
  monitorState,

  type StageStatusInfo,
  type TimelineEntry,
  toStageStatusInfo,
} from './persist-monitor'

// ─── 辅助函数 ─────────────────────────────────────────────────

/** 解析会话显示名称（附加 groupId/userId 后缀以区分同名会话） */
export function resolveSessionDisplayName({
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
}): string {
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

/** 从 TimelineEntry.id 提取序列号（用于同时间戳排序） */
function getTimelineEntrySequence(entry: TimelineEntry): number {
  const match = /^evt_(\d+)_/.exec(entry.id)
  return match ? Number(match[1]) : 0
}

/** 时间线条目比较器（先按 timestamp，同时间戳按序列号） */
export function compareTimelineEntries(a: TimelineEntry, b: TimelineEntry): number {
  if (a.timestamp !== b.timestamp) {
    return a.timestamp - b.timestamp
  }
  return getTimelineEntrySequence(a) - getTimelineEntrySequence(b)
}

// ─── 状态更新函数 ─────────────────────────────────────────────

/** 追加时间线条目（超 MAX_TIMELINE_ENTRIES 丢弃最旧） */
export function appendTimelineEntry(entry: TimelineEntry): void {
  const next = [...monitorState.timeline, entry].sort(compareTimelineEntries)
  monitorState.timeline = next.length > MAX_TIMELINE_ENTRIES
    ? next.slice(next.length - MAX_TIMELINE_ENTRIES)
    : next
}

/** 更新会话概要信息（session.start 新建，其余事件更新 lastActivity/eventCount） */
export function updateSessionInfo(event: MaisakaMonitorEvent, sessionId: string, timestamp: number): void {
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

  const next = new Map(monitorState.sessions)
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

  monitorState.sessions = next
}

/** 批量应用阶段状态快照（按 updatedAt 比较新旧——旧不覆盖新） */
function applyStatusIfFresh(next: Map<string, StageStatusInfo>, status: StageStatusInfo): void {
  const existing = next.get(status.sessionId)
  if (existing && status.updatedAt < existing.updatedAt) {
    return
  }
  next.set(status.sessionId, status)
}

/** 更新阶段状态（stage.status / stage.removed / stage.snapshot） */
export function updateStageStatus(event: MaisakaMonitorEvent): void {
  if (event.type === 'stage.snapshot') {
    const rawEntries = (event.data as unknown as Record<string, unknown>).entries
    if (!Array.isArray(rawEntries)) {
      return
    }
    const next = new Map(monitorState.stageStatuses)
    for (const rawEntry of rawEntries) {
      if (!rawEntry || typeof rawEntry !== 'object') {
        continue
      }
      const status = toStageStatusInfo(rawEntry as Record<string, unknown>)
      if (status) {
        applyStatusIfFresh(next, status)
      }
    }
    monitorState.stageStatuses = next
    return
  }

  if (event.type === 'stage.status') {
    const status = toStageStatusInfo(event.data as unknown as Record<string, unknown>)
    if (!status) {
      return
    }
    const next = new Map(monitorState.stageStatuses)
    applyStatusIfFresh(next, status)
    monitorState.stageStatuses = next
    return
  }

  if (event.type === 'stage.removed') {
    const dataRecord = event.data as unknown as Record<string, unknown>
    const sessionId = typeof dataRecord.session_id === 'string' ? dataRecord.session_id : ''
    if (!sessionId) {
      return
    }
    const next = new Map(monitorState.stageStatuses)
    next.delete(sessionId)
    monitorState.stageStatuses = next
  }
}

/**
 * 按 message_id 匹配更新既有时间线条目的 content/reply_to/media。
 * @returns 更新条目的 entryId（匹配不到返回 null——不新增条目）
 */
export function updateTimelineMessageContent(event: MaisakaMonitorEvent, sessionId: string): string | null {
  if (event.type !== 'message.updated') {
    return null
  }

  const dataRecord = event.data as unknown as Record<string, unknown>
  const messageId = typeof dataRecord.message_id === 'string' ? dataRecord.message_id : ''
  const content = typeof dataRecord.content === 'string' ? dataRecord.content : ''
  const replyTo = dataRecord.reply_to
  const media = Array.isArray(dataRecord.media) ? dataRecord.media : []
  if (!messageId) {
    return null
  }

  let updatedEntryId = ''
  const nextTimeline = monitorState.timeline.map((entry) => {
    if (
      entry.sessionId !== sessionId
      || (entry.type !== 'message.ingested' && entry.type !== 'message.sent')
    ) {
      return entry
    }

    const entryData = entry.data as unknown as Record<string, unknown>
    if (entryData.message_id !== messageId) {
      return entry
    }

    updatedEntryId = entry.id
    return {
      ...entry,
      data: {
        ...entryData,
        content,
        reply_to: replyTo,
        media,
      } as TimelineEntry['data'],
    }
  })

  if (!updatedEntryId) {
    return null
  }

  monitorState.timeline = nextTimeline
  return updatedEntryId
}

// ─── 统计聚合 ─────────────────────────────────────────────────

/** 从时间线聚合统计信息 */
export function computeMonitorStats(timeline: TimelineEntry[]): {
  messages: number
  cycles: number
  toolCalls: number
} {
  let messages = 0
  let cycles = 0
  let toolCalls = 0

  for (const entry of timeline) {
    if (entry.type === 'message.ingested' || entry.type === 'message.sent') {
      messages += 1
    } else if (entry.type === 'planner.finalized') {
      cycles += 1
      const data = entry.data as unknown as Record<string, unknown>
      const tools = data.tools
      if (Array.isArray(tools)) {
        toolCalls += tools.length
      }
    }
  }

  return { messages, cycles, toolCalls }
}