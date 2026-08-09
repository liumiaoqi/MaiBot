import type {
  ReasoningPromptFile,
  ReasoningPromptMessageAvatar,
  ReasoningPromptSessionInfo,
} from '@/lib/reasoning-process-api'

import {
  formatStageName,
  isRecord,
  stringifyPromptContent,
  type StructuredPromptMessage,
  type StructuredPromptPayload,
} from './format'

export type ParsedMessageTagBlock = {
  type: 'message'
  attrs: Record<string, string>
  body: string
}

export type ParsedTextBlock = {
  type: 'text'
  text: string
}

export type ParsedNaturalTextBlock = ParsedMessageTagBlock | ParsedTextBlock

export type ToolParameterView = {
  name: string
  type: string
  description: string
  required: boolean
  enumValues: string[]
  defaultValue: string
}

export type ToolDefinitionView = {
  name: string
  type: string
  description: string
  parameters: ToolParameterView[]
  raw: unknown
}

export type ReasoningPromptMessageAvatarMap = Record<string, ReasoningPromptMessageAvatar>

export type ReasoningHeaderMeta = {
  sessionId: string
  callId: string
  remainingText: string
}

export type ToolCallDisplayItem = {
  id: string
  name: string
  arguments: unknown
  source: string
  sourceLabel: string
}

export function normalizeToolCallForDisplay(toolCall: unknown): ToolCallDisplayItem {
  const toolRecord = isRecord(toolCall) ? toolCall : {}
  const functionRecord = isRecord(toolRecord.function) ? toolRecord.function : {}
  const extraContent = isRecord(toolRecord.extra_content) ? toolRecord.extra_content : {}
  const rawSource = String(toolRecord.source || toolRecord.tool_call_source || extraContent.tool_call_source || '').trim()
  const normalizedSource = rawSource.toLowerCase()
  const sourceLabel = normalizedSource === 'reasoning'
    ? '推理中调用'
    : normalizedSource === 'response'
      ? '正文调用'
      : String(toolRecord.source_label || toolRecord.tool_call_source_label || '').trim()
  return {
    id: String(toolRecord.id || toolRecord.call_id || ''),
    name: String(functionRecord.name || toolRecord.name || toolRecord.func_name || 'unknown'),
    arguments: functionRecord.arguments ?? toolRecord.arguments ?? toolRecord.args ?? {},
    source: normalizedSource,
    sourceLabel,
  }
}

export function getToolCallSourceClassName(source: string): string {
  if (source === 'reasoning') {
    return 'border-teal-500/45 bg-teal-500/10 text-teal-700 dark:text-teal-300'
  }
  if (source === 'response') {
    return 'border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300'
  }
  return 'border-muted-foreground/30 bg-muted/40 text-muted-foreground'
}

export function formatSchemaType(schema: Record<string, unknown>): string {
  const rawType = schema.type
  if (Array.isArray(rawType)) return rawType.map(String).join(' | ')
  if (typeof rawType === 'string') return rawType
  if (isRecord(schema.items)) return `${formatSchemaType(schema.items)}[]`
  if (schema.enum) return 'enum'
  return 'unknown'
}

export function formatSchemaValue(value: unknown): string {
  if (value === undefined) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item))
}

export function normalizeToolDefinition(toolDefinition: unknown): ToolDefinitionView {
  const toolRecord = isRecord(toolDefinition) ? toolDefinition : {}
  const functionRecord = isRecord(toolRecord.function) ? toolRecord.function : toolRecord
  const parametersRecord = isRecord(functionRecord.parameters) ? functionRecord.parameters : {}
  const propertiesRecord = isRecord(parametersRecord.properties) ? parametersRecord.properties : {}
  const requiredNames = new Set(toStringList(parametersRecord.required))

  const parameters = Object.entries(propertiesRecord).map(([name, rawSchema]) => {
    const schema = isRecord(rawSchema) ? rawSchema : {}
    return {
      name,
      type: formatSchemaType(schema),
      description: typeof schema.description === 'string' ? schema.description : '',
      required: requiredNames.has(name),
      enumValues: toStringList(schema.enum),
      defaultValue: formatSchemaValue(schema.default),
    }
  })

  return {
    name: typeof functionRecord.name === 'string' ? functionRecord.name : '未命名工具',
    type: typeof toolRecord.type === 'string' ? toolRecord.type : 'function',
    description: typeof functionRecord.description === 'string' ? functionRecord.description : '',
    parameters,
    raw: toolDefinition,
  }
}

export function normalizeDisplayName(name: string): string {
  return name.trim().toLowerCase()
}

export function extractBotSelfNames(prompt: StructuredPromptPayload | null): Set<string> {
  const names = new Set<string>(['麦麦'])

  for (const message of prompt?.messages ?? []) {
    if (String(message.role || '').toLowerCase() !== 'system') continue
    const content = stringifyPromptContent(message.content)
    const focusMatch = content.match(/你需要关注\s+(.+?)\s+与用户/)
    const nameMatch = content.match(/你的名字是([^，。,.\n]+)/)
    const aliasMatch = content.match(/也有人叫你([^。\n]+)/)

    for (const match of [focusMatch, nameMatch]) {
      const name = match?.[1]?.trim()
      if (name) names.add(name)
    }

    if (aliasMatch?.[1]) {
      aliasMatch[1]
        .split(/[、,，]/)
        .map((alias) => alias.trim())
        .filter(Boolean)
        .forEach((alias) => names.add(alias))
    }
  }

  return new Set(Array.from(names).map(normalizeDisplayName).filter(Boolean))
}

export function decodeSimpleHtmlEntity(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

export function parseMessageTagAttributes(rawAttributes: string): Record<string, string> {
  const attrs: Record<string, string> = {}
  const attributePattern = /([A-Za-z_][\w:-]*)\s*=\s*"([^"]*)"/g
  for (const match of rawAttributes.matchAll(attributePattern)) {
    attrs[match[1]] = decodeSimpleHtmlEntity(match[2])
  }
  return attrs
}

export function getFirstMessageTagAttrs(text: string): Record<string, string> {
  const match = text.match(/<message\b([^>]*)>/i)
  return match ? parseMessageTagAttributes(match[1] ?? '') : {}
}

export function isBotSelfStructuredMessage(message: StructuredPromptMessage, botSelfNames: Set<string>): boolean {
  if (String(message.role || '').toLowerCase() !== 'user') return false

  const text = stringifyPromptContent(message.content)
  const user = getFirstMessageTagAttrs(text).user
  return Boolean(user && botSelfNames.has(normalizeDisplayName(user)))
}

export function formatSessionType(chatType: string): string {
  if (chatType === 'group') return '群聊'
  if (chatType === 'private') return '私聊'
  return '未知类型'
}

export function getSessionDisplayName(
  sessionName: string,
  sessionInfo?: ReasoningPromptSessionInfo,
  fallbackName?: string | null
): string {
  return sessionInfo?.display_name || fallbackName || sessionName
}

export function getSessionSubtitle(sessionInfo?: ReasoningPromptSessionInfo): string {
  if (!sessionInfo) return ''

  const parts = []
  if (sessionInfo.platform) {
    parts.push(`${sessionInfo.platform} · ${formatSessionType(sessionInfo.chat_type)}`)
  }
  if (sessionInfo.resolved_session_id) {
    parts.push(`会话 ${sessionInfo.resolved_session_id.slice(0, 8)}`)
  } else {
    parts.push('未解析到真实会话')
  }
  return parts.join(' · ')
}

export function extractReasoningHeaderMeta(text?: string): ReasoningHeaderMeta {
  const meta: ReasoningHeaderMeta = {
    sessionId: '',
    callId: '',
    remainingText: '',
  }
  if (!text) return meta

  const remainingLines: string[] = []
  for (const line of text.split(/\r?\n/)) {
    const normalizedLine = line.trim()
    const sessionMatch = normalizedLine.match(/^会话\s*ID[：:]\s*(.+)$/i)
    if (sessionMatch) {
      meta.sessionId = sessionMatch[1].trim()
      continue
    }

    const callMatch = normalizedLine.match(/^调用\s*ID[：:]\s*(.+)$/i)
    if (callMatch) {
      meta.callId = callMatch[1].trim()
      continue
    }

    remainingLines.push(line)
  }

  meta.remainingText = remainingLines.join('\n').trim()
  return meta
}

export function getReasoningRecordTitle(
  item: ReasoningPromptFile,
  sessionInfo?: ReasoningPromptSessionInfo
): string {
  const platform = item.platform || sessionInfo?.platform || ''
  const chatType = item.chat_type || sessionInfo?.chat_type || ''
  const targetId = item.target_id || sessionInfo?.target_id || ''
  const parts = [
    formatStageName(item.stage),
    getSessionDisplayName(item.session_id, sessionInfo, item.session_display_name),
    item.display_title || item.stem,
  ]

  if (platform && chatType && targetId) {
    parts.push(platform, formatSessionType(chatType), targetId)
  }

  return parts.join('/')
}

export function formatPromptPreviewText(previewText: string): string {
  return previewText.replace(/^动作[：:]\s*/, '')
}

export function buildAvatarFallbackText(displayName: string, userId: string): string {
  const normalizedName = displayName.trim()
  if (normalizedName) return normalizedName.slice(0, 1).toUpperCase()
  const normalizedUserId = userId.trim()
  return normalizedUserId ? normalizedUserId.slice(-2) : '用'
}

export function parseNaturalTextBlocks(text: string): ParsedNaturalTextBlock[] {
  const messageTagPattern = /<message\b([^>]*)>/gi
  const matches = Array.from(text.matchAll(messageTagPattern))
  if (matches.length === 0) {
    return [{ type: 'text', text }]
  }

  const blocks: ParsedNaturalTextBlock[] = []
  let cursor = 0
  matches.forEach((match, index) => {
    const start = match.index ?? 0
    if (start > cursor) {
      blocks.push({ type: 'text', text: text.slice(cursor, start) })
    }

    const bodyStart = start + match[0].length
    const nextStart = matches[index + 1]?.index ?? text.length
    const body = text.slice(bodyStart, nextStart).replace(/<\/message>\s*$/i, '').trim()
    blocks.push({
      type: 'message',
      attrs: parseMessageTagAttributes(match[1] ?? ''),
      body,
    })
    cursor = nextStart
  })

  if (cursor < text.length) {
    blocks.push({ type: 'text', text: text.slice(cursor) })
  }

  return blocks.filter((block) => (block.type === 'message' ? block.body || Object.keys(block.attrs).length > 0 : block.text.trim()))
}