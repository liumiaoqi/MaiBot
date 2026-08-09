import type { ReasoningReplayResponse } from '@/lib/reasoning-process-api'

import {
  formatDurationMs,
  isRecord,
  stringifyPromptContent,
  type StructuredPromptPayload,
} from './format'

export type EditableReplayMessage = {
  id: string
  role: string
  contentText: string
  originalContent: unknown
  tool_call_id?: string
  tool_calls?: unknown[]
}

export type ReplayRunResult = {
  id: string
  index: number
  result: ReasoningReplayResponse | null
  error: string | null
}

export function hasReplayableImageReference(value: Record<string, unknown>): boolean {
  if (typeof value.image_base64 === 'string' && value.image_base64.trim()) {
    return true
  }

  const rawImageUrl = isRecord(value.image_url) ? value.image_url.url : value.image_url
  if (typeof rawImageUrl === 'string' && rawImageUrl.startsWith('data:image/')) {
    return true
  }

  const imageReference = isRecord(value.image_reference) ? value.image_reference : {}
  return Boolean(
    (typeof value.image_path === 'string' && value.image_path.trim()) ||
      (typeof value.image_uri === 'string' && value.image_uri.trim()) ||
      (typeof imageReference.image_path === 'string' && imageReference.image_path.trim()) ||
      (typeof imageReference.image_uri === 'string' && imageReference.image_uri.trim())
  )
}

export function hasUnreplayableImagePart(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasUnreplayableImagePart)
  }
  if (!isRecord(value)) {
    return false
  }

  const partType = String(value.type || '').trim().toLowerCase()
  if (['image', 'image_url', 'input_image'].includes(partType)) {
    return !hasReplayableImageReference(value)
  }

  return Object.values(value).some(hasUnreplayableImagePart)
}

export function createEditableReplayMessages(prompt: StructuredPromptPayload | null): EditableReplayMessage[] {
  return (prompt?.messages ?? []).map((message, index) => {
    const shouldUseTextFallback = hasUnreplayableImagePart(message.content)
    const originalContent = shouldUseTextFallback ? stringifyPromptContent(message.content) : message.content ?? ''
    return {
      id: `${message.index ?? index + 1}-${message.role ?? 'unknown'}-${index}`,
      role: String(message.role || 'user'),
      contentText: typeof originalContent === 'string' ? originalContent : stringifyPromptContent(originalContent),
      originalContent,
      tool_call_id: message.tool_call_id,
      tool_calls: message.tool_calls,
    }
  })
}

export function createBlankReplayMessage(): EditableReplayMessage {
  return {
    id: `manual-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    role: 'user',
    contentText: '',
    originalContent: '',
  }
}

export function parseReplayMessageContent(contentText: string, originalContent: unknown): unknown {
  if (typeof originalContent === 'string' || originalContent === null || originalContent === undefined) {
    return contentText
  }

  const trimmedContent = contentText.trim()
  if (!trimmedContent) {
    return ''
  }

  try {
    return JSON.parse(trimmedContent) as unknown
  } catch {
    return contentText
  }
}

export function formatReplayTokenSummary(result: ReasoningReplayResponse): string {
  const parts = [
    `输入 ${result.prompt_tokens}`,
    `输出 ${result.completion_tokens}`,
    `总计 ${result.total_tokens}`,
  ]
  if (result.prompt_cache_hit_tokens > 0 || result.prompt_cache_miss_tokens > 0) {
    parts.push(`缓存命中 ${result.prompt_cache_hit_tokens}`)
  }
  if (result.duration_ms > 0) {
    parts.push(`耗时 ${formatDurationMs(result.duration_ms)}`)
  }
  return parts.join(' · ')
}

export function formatEmptyReplayResponseHint(result: ReasoningReplayResponse): string {
  const hasReasoning = result.reasoning.trim().length > 0
  const hasToolCalls = Boolean(result.tool_calls && result.tool_calls.length > 0)
  if (hasReasoning && hasToolCalls) {
    return '模型未返回正文，已返回推理内容和工具调用。'
  }
  if (hasReasoning) {
    return '模型未返回正文，已返回推理内容。'
  }
  if (hasToolCalls) {
    return '模型未返回正文，已返回工具调用。'
  }
  return '模型未返回正文。'
}