import type { CSSProperties } from 'react'

import type {
  ReasoningPromptFile,
  ReasoningPromptStageInfo,
} from '@/lib/reasoning-process-api'

export const CORE_STAGE_NAMES = ['planner', 'replyer']
export const REMOVED_STAGE_NAMES = ['timing_gate']

export const NATURAL_LANGUAGE_TEXT_STYLE: CSSProperties = {
  fontFamily:
    "'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', system-ui, sans-serif",
}

export const STAGE_LABELS: Record<string, string> = {
  emotion: '表情包发送',
  expression_learner: '表达学习',
  expression_selection: '表达选择',
  expression_selector: '表达选择',
  jargon_learner: '黑话抽取',
  jargon_learning_update: '黑话含义推断',
  planner: '思维管道',
  reply_effect_judge: '回复效果评估',
  replyer: '回复器',
  thinking_organ: '思维管道',
  tool_loop: '工具循环',
  timing_gate: '时机判断（历史）',
}

export type StageCategoryRow = {
  key: string
  label: string
  items: ReasoningPromptStageInfo[]
  collapsedByDefault?: boolean
}

export type StructuredPromptMessage = {
  index?: number
  role?: string
  content?: unknown
  tool_call_id?: string
  tool_calls?: unknown[]
}

export type StructuredPromptOutput = {
  title?: string
  content?: unknown
  tool_calls?: unknown[]
}

export type StructuredPromptLlmCall = {
  inference_stage: string
  request?: {
    kind?: string
    selection_reason?: string
  }
  metadata?: {
    model_name?: string
    duration_ms?: number
  }
  messages?: StructuredPromptMessage[]
  output?: StructuredPromptOutput | null
}

export type StructuredPromptPayload = {
  schema_version?: number
  request?: {
    kind?: string
    selection_reason?: string
  }
  metadata?: {
    model_name?: string
    duration_ms?: number
  }
  messages?: StructuredPromptMessage[]
  output?: StructuredPromptOutput | null
  tool_definitions?: unknown[]
  jargon_learning_calls?: StructuredPromptLlmCall[]
}

export function getInitialSearchParams(): URLSearchParams {
  if (typeof window === 'undefined') return new URLSearchParams()
  return new URLSearchParams(window.location.search)
}

export function getSafeInternalReturnTo(value: string | null): string {
  const normalized = value?.trim() ?? ''
  if (!normalized || !normalized.startsWith('/') || normalized.startsWith('//') || typeof window === 'undefined') {
    return ''
  }

  try {
    const url = new URL(normalized, window.location.origin)
    if (url.origin !== window.location.origin) return ''
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return ''
  }
}

export function formatStageName(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

export function isLearnerStage(stage: string): boolean {
  return stage.includes('learner') || stage.includes('learning')
}

export function buildStageCategoryRows(stageCards: ReasoningPromptStageInfo[]): StageCategoryRow[] {
  const stageInfoByName = new Map(stageCards.map((item) => [item.name, item]))
  const usedStageNames = new Set<string>()
  const takeNamedStages = (stageNames: string[]) => stageNames.flatMap((stageName) => {
    const item = stageInfoByName.get(stageName)
    if (!item) return []
    usedStageNames.add(stageName)
    return [item]
  })
  const takeMatchingStages = (predicate: (stage: string) => boolean) => stageCards.filter((item) => {
    if (usedStageNames.has(item.name) || !predicate(item.name)) return false
    usedStageNames.add(item.name)
    return true
  })

  const coreStages = takeNamedStages(CORE_STAGE_NAMES)
  const learnerStages = takeMatchingStages(isLearnerStage)
  const removedStages = takeNamedStages(REMOVED_STAGE_NAMES)
  const otherStages = takeMatchingStages(() => true)

  return [
    { key: 'core', label: '主流程', items: coreStages },
    { key: 'learners', label: '学习器', items: learnerStages },
    { key: 'others', label: '其余', items: otherStages },
    { key: 'removed', label: '不再使用', items: removedStages, collapsedByDefault: true },
  ].filter((row) => row.items.length > 0)
}

export function formatTime(timestamp: number | null, modifiedAt: number): string {
  const value = timestamp ? timestamp : modifiedAt * 1000
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function formatDurationMs(durationMs: number | null): string {
  if (durationMs === null || !Number.isFinite(durationMs)) return ''
  if (durationMs < 1000) return `${durationMs.toFixed(durationMs >= 100 ? 0 : 1)} ms`
  return `${(durationMs / 1000).toFixed(2)} s`
}

export function getReasoningMetadataText(item: ReasoningPromptFile): string {
  const parts: string[] = []
  if (item.model_name) {
    parts.push(`模型：${item.model_name}`)
  }
  const durationText = formatDurationMs(item.duration_ms)
  if (durationText) {
    parts.push(`耗时：${durationText}`)
  }
  return parts.join(' · ')
}

export function getStructuredPromptMessageRoleStyle(role?: string, isBotSelf = false): {
  label: string
  containerClassName: string
  badgeClassName: string
} {
  const normalizedRole = String(role || '').trim().toLowerCase()
  if (isBotSelf) {
    return {
      label: role || 'user',
      containerClassName: 'border-orange-300/70 bg-orange-50/75 dark:border-orange-700/60 dark:bg-orange-950/25',
      badgeClassName:
        'border-orange-400/70 bg-orange-100/85 text-orange-900 dark:border-orange-700 dark:bg-orange-950 dark:text-orange-100',
    }
  }
  if (normalizedRole === 'system') {
    return {
      label: 'system',
      containerClassName: 'border-cyan-300/70 bg-cyan-50/70 dark:border-cyan-700/60 dark:bg-cyan-950/25',
      badgeClassName: 'border-cyan-400/70 bg-cyan-100/80 text-cyan-900 dark:border-cyan-700 dark:bg-cyan-950 dark:text-cyan-100',
    }
  }
  if (normalizedRole === 'user') {
    return {
      label: 'user',
      containerClassName: 'border-emerald-300/70 bg-emerald-50/70 dark:border-emerald-700/60 dark:bg-emerald-950/25',
      badgeClassName:
        'border-emerald-400/70 bg-emerald-100/80 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100',
    }
  }
  if (normalizedRole === 'assistant') {
    return {
      label: 'assistant',
      containerClassName: 'border-amber-300/70 bg-amber-50/70 dark:border-amber-700/60 dark:bg-amber-950/25',
      badgeClassName:
        'border-amber-400/70 bg-amber-100/80 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100',
    }
  }
  if (normalizedRole === 'tool') {
    return {
      label: 'tool',
      containerClassName: 'border-violet-300/70 bg-violet-50/70 dark:border-violet-700/60 dark:bg-violet-950/25',
      badgeClassName:
        'border-violet-400/70 bg-violet-100/80 text-violet-900 dark:border-violet-700 dark:bg-violet-950 dark:text-violet-100',
    }
  }

  return {
    label: role || '未知角色',
    containerClassName: 'bg-muted/30',
    badgeClassName: 'bg-background/80',
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

export function stringifyStructuredValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  return JSON.stringify(value, null, 2)
}

export function stringifyPromptContent(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  if (!Array.isArray(value)) return stringifyStructuredValue(value)

  return value
    .map((item) => {
      if (typeof item === 'string') return item
      if (isRecord(item) && item.type === 'text' && typeof item.text === 'string') return item.text
      if (isRecord(item)) {
        const partType = String(item.type || '').trim().toLowerCase()
        if (['image', 'image_url', 'input_image'].includes(partType)) {
          const imageFormat = String(item.image_format || item.format || 'unknown').trim() || 'unknown'
          const sizeText = typeof item.size_bytes === 'number' ? ` ${item.size_bytes} B` : ''
          return `[图片 image/${imageFormat}${sizeText}]`
        }
      }
      return stringifyStructuredValue(item)
    })
    .filter(Boolean)
    .join('\n')
    .trim()
}

export function parseStructuredPrompt(content: string): StructuredPromptPayload | null {
  if (!content.trim()) return null
  try {
    const payload = JSON.parse(content) as unknown
    if (payload && typeof payload === 'object') return payload as StructuredPromptPayload
  } catch {
    return null
  }
  return null
}

export function extractJargonInferenceStage(payload: StructuredPromptPayload, fallbackIndex: number): string {
  const selectionReason = payload.request?.selection_reason ?? ''
  const stageLine = selectionReason
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line.startsWith('推断阶段:'))
  if (stageLine) {
    return stageLine.split(':', 2)[1]?.trim() || `stage_${fallbackIndex + 1}`
  }
  return `stage_${fallbackIndex + 1}`
}

export function combineJargonLearningUpdatePayloads(
  payloads: StructuredPromptPayload[],
  displayTitle: string
): StructuredPromptPayload {
  const jargonLearningCalls = payloads.map((payload, payloadIndex) => ({
    inference_stage: extractJargonInferenceStage(payload, payloadIndex),
    request: payload.request,
    metadata: payload.metadata,
    messages: payload.messages ?? [],
    output: payload.output ?? null,
  }))

  return {
    schema_version: 3,
    request: {
      kind: 'jargon_learning_update',
      selection_reason: `词条: ${displayTitle || '未知黑话'}\n包含 ${payloads.length} 次黑话含义推断调用。`,
    },
    metadata: payloads[0]?.metadata ?? {},
    messages: [],
    output: null,
    tool_definitions: [],
    jargon_learning_calls: jargonLearningCalls,
  }
}

export function buildStructuredPromptCopyText(payload: StructuredPromptPayload | null): string {
  if (!payload) return ''

  const sections: string[] = []
  const metadataLines: string[] = []
  if (payload.request?.kind) metadataLines.push(`请求类型：${payload.request.kind}`)
  if (payload.request?.selection_reason) metadataLines.push(`选择原因：${payload.request.selection_reason}`)
  if (payload.metadata?.model_name) metadataLines.push(`模型：${payload.metadata.model_name}`)
  if (typeof payload.metadata?.duration_ms === 'number') metadataLines.push(`耗时：${payload.metadata.duration_ms} ms`)
  if (metadataLines.length > 0) sections.push(`[元信息]\n${metadataLines.join('\n')}`)

  if (payload.output) {
    const outputText = stringifyPromptContent(payload.output.content)
    const toolCallsText = payload.output.tool_calls?.length
      ? `\n\n[工具调用]\n${stringifyStructuredValue(payload.output.tool_calls)}`
      : ''
    if (outputText || toolCallsText) {
      sections.push(`[${payload.output.title || '输出结果'}]\n${outputText}${toolCallsText}`)
    }
  }

  const messageSections = (payload.messages ?? []).map((message, index) => {
    const role = message.role || 'unknown'
    const content = stringifyPromptContent(message.content)
    const toolCallId = message.tool_call_id ? `\ntool_call_id: ${message.tool_call_id}` : ''
    const toolCalls = message.tool_calls?.length
      ? `\ntool_calls:\n${stringifyStructuredValue(message.tool_calls)}`
      : ''
    return `#${message.index ?? index + 1} ${role}${toolCallId}${toolCalls}\n${content}`
  })
  if (messageSections.length > 0) sections.push(`[Prompt 消息]\n${messageSections.join('\n\n')}`)

  if (payload.tool_definitions?.length) {
    sections.push(`[工具定义]\n${stringifyStructuredValue(payload.tool_definitions)}`)
  }

  return sections.join(`\n\n${'='.repeat(80)}\n\n`)
}