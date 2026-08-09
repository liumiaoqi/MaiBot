/**
 * talk-frequency 工具函数 + 类型 + 常量（R3-2-2）
 *
 * 从 dashboard routes/chat-management.tsx 404-521 行搬移。
 * 包含：时间轴分钟解析/格式化 / 时间段分割 / 拖拽坐标转换 / 频率值颜色 / 精确规则提取。
 */
import type {
  ChatStreamDetail,
  ChatTalkFrequencyRule,
} from '@/lib/chat-management-api'

/** 编辑模式 */
export type TalkFrequencyEditMode = 'input' | 'timeline'

/** 时间轴拖拽边 */
export type TimelineEdge = 'end' | 'start'

/** 时间段范围（分钟） */
export interface TimelineRange {
  end: number
  start: number
}

/** 一天分钟数 */
export const DAY_MINUTES = 24 * 60

/** 时间轴刻度（整点） */
export const TIMELINE_TICKS = [0, 3, 6, 9, 12, 15, 18, 21, 24] as const

/** 拖拽步进（5 分钟） */
export const TIMELINE_DRAG_STEP_MINUTES = 5

/** 钳制频率值到 [0, 1] */
export function clampTalkFrequencyValue(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.min(1, value))
}

/** 解析 HH:MM 为分钟数 */
export function parseTimelineMinute(value: string): number | null {
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(value.trim())
  if (!match) {
    return null
  }
  const hour = Number(match[1])
  const minute = Number(match[2])
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) {
    return null
  }
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return null
  }
  return hour * 60 + minute
}

/** 格式化分钟数为 HH:MM */
export function formatTimelineMinute(minute: number): string {
  const normalizedMinute = Math.max(0, Math.min(DAY_MINUTES - 1, Math.round(minute)))
  const hour = Math.floor(normalizedMinute / 60)
  const minuteInHour = normalizedMinute % 60
  return `${hour.toString().padStart(2, '0')}:${minuteInHour.toString().padStart(2, '0')}`
}

/** 解析时间段字符串（HH:MM-HH:MM 或 *） */
export function parseTalkTimeRange(time: string): TimelineRange | null {
  const normalizedTime = time.trim()
  if (!normalizedTime || normalizedTime === '*') {
    return { start: 0, end: DAY_MINUTES - 1 }
  }
  const [startRaw, endRaw, extra] = normalizedTime.split('-')
  if (extra !== undefined) {
    return null
  }
  const start = startRaw ? parseTimelineMinute(startRaw) : null
  const end = endRaw ? parseTimelineMinute(endRaw) : null
  if (start === null || end === null) {
    return null
  }
  return { start, end }
}

/** 格式化时间段为字符串 */
export function formatTalkTimeRange(range: TimelineRange): string {
  return `${formatTimelineMinute(range.start)}-${formatTimelineMinute(range.end)}`
}

/** 计算时间段在时间轴上的视觉分段（跨午夜返回两段） */
export function getTimelineSegments(range: TimelineRange): Array<{ left: number; width: number }> {
  if (range.start <= range.end) {
    return [
      {
        left: (range.start / DAY_MINUTES) * 100,
        width: ((range.end - range.start + 1) / DAY_MINUTES) * 100,
      },
    ]
  }
  return [
    {
      left: (range.start / DAY_MINUTES) * 100,
      width: ((DAY_MINUTES - range.start) / DAY_MINUTES) * 100,
    },
    {
      left: 0,
      width: ((range.end + 1) / DAY_MINUTES) * 100,
    },
  ]
}

/** 从客户端 X 坐标计算时间轴分钟（对齐到步进） */
export function getTimelineMinuteFromClient(clientX: number, timelineElement: HTMLElement): number {
  const rect = timelineElement.getBoundingClientRect()
  const ratio = rect.width > 0 ? (clientX - rect.left) / rect.width : 0
  const rawMinute = Math.max(0, Math.min(DAY_MINUTES - 1, ratio * DAY_MINUTES))
  return Math.round(rawMinute / TIMELINE_DRAG_STEP_MINUTES) * TIMELINE_DRAG_STEP_MINUTES
}

/** 频率值对应颜色 */
export function talkValueColor(value: number): string {
  if (value >= 0.75) {
    return 'bg-emerald-500'
  }
  if (value >= 0.45) {
    return 'bg-amber-500'
  }
  return 'bg-sky-500'
}

/** 提取当前聊天流的精确规则 */
export function getExactTalkRules(detail: ChatStreamDetail): ChatTalkFrequencyRule[] {
  return detail.talk_frequency.matched_rules.filter((rule) => {
    return (
      String(rule.platform || '').trim() === detail.platform &&
      String(rule.item_id || '').trim() === detail.target_id &&
      String(rule.type || '').trim() === detail.chat_type
    )
  })
}

/** 格式化频率摘要（保留两位小数） */
export function formatFrequencySummary(label: string): string {
  const numericValue = Number.parseFloat(label)
  if (!Number.isFinite(numericValue)) {
    return label
  }
  return numericValue.toFixed(2)
}