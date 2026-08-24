/**
 * TimelineEntryItem 单条时间线渲染
 *
 * 按 entry.type 分派到 MessageEntry / PlannerEntry。
 * 导出工具函数 formatMs / formatTimestamp / formatRelativeTime 供其他组件复用。
 *
 * 循环导入说明：本文件导入 message-entry/planner-entry，它们反向导入工具函数。
 * 工具函数用 `export function` 形式（hoisting），ESM live binding 安全。
 */
import type { TimelineEntry } from '../hooks/persist-monitor'
import type { MessageIngestedEvent, MessageSentEvent, PlannerFinalizedEvent } from '@/lib/maisaka-monitor-client'

import { MessageEntry } from './message-entry'
import { PlannerEntry } from './planner-entry'

// ─── 工具函数 ─────────────────────────────────────────────────

/** 毫秒格式化（<1s 显示 ms，≥1s 显示 s） */
export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/** 时间戳格式化（秒级 → HH:mm:ss） */
export function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** 相对时间格式化（返回 i18n key + 插值参数，调用方用 t() 渲染） */
export interface RelativeTimeLabel {
  key: string
  options?: Record<string, unknown>
}

export function formatRelativeTime(ts: number): RelativeTimeLabel {
  const diff = Date.now() / 1000 - ts
  if (diff < 10) return { key: 'monitor.maisaka.justNow' }
  if (diff < 60) return { key: 'monitor.maisaka.secondsAgo', options: { count: Math.round(diff) } }
  if (diff < 3600) return { key: 'monitor.maisaka.minutesAgo', options: { count: Math.round(diff / 60) } }
  return { key: 'monitor.maisaka.hoursAgo', options: { count: Math.round(diff / 3600) } }
}

// ─── 分派组件 ─────────────────────────────────────────────────

export interface TimelineEntryItemProps {
  entry: TimelineEntry
}

export function TimelineEntryItem({ entry }: TimelineEntryItemProps) {
  switch (entry.type) {
    case 'message.ingested':
      return <MessageEntry data={entry.data as MessageIngestedEvent} kind="ingested" />
    case 'message.sent':
      return <MessageEntry data={entry.data as MessageSentEvent} kind="sent" />
    case 'planner.finalized':
      return <PlannerEntry data={entry.data as PlannerFinalizedEvent} />
    default:
      return null
  }
}