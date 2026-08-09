/**
 * chat-management 工具函数（R3-2-1）
 *
 * 从 dashboard routes/chat-management.tsx 105-198 + 267-304 行搬移。
 * 包含：时间戳格式化 / 聊天类型标签 / 目标规范化 / 互组序列化 / 搜索过滤。
 */
import type {
  ChatConfigRule,
  ChatStream,
  ChatStreamType,
} from '@/lib/chat-management-api'

/** 聊天管理视图类型 */
export type ChatManagementView = 'groups' | 'streams'

/** 聊天类型筛选 */
export type ChatTypeFilter = 'all' | ChatStreamType

/** 互组类型 */
export type MutualGroupKind = 'expression' | 'jargon' | 'memory'

/** 学习类型 */
export type LearningKind = 'expression' | 'jargon'

/** 互组聊天搜索结果上限 */
export const MUTUAL_GROUP_CHAT_RESULT_LIMIT = 50

/** 互组类型标签 */
export const MUTUAL_GROUP_KIND_LABEL: Record<MutualGroupKind, string> = {
  expression: '表达',
  jargon: '黑话',
  memory: '记忆',
}

/** 目标项（互组成员） */
export interface TargetItem {
  platform: string
  item_id: string
  rule_type?: ChatStreamType | string
  type?: ChatStreamType | string
}

/** 聊天流组配置 */
export interface ChatStreamGroupConfig {
  targets?: TargetItem[]
  expression_groups?: TargetItem[]
  jargon_groups?: TargetItem[]
}

/** 格式化时间戳（秒→MM-DD HH:mm） */
export function formatTimestamp(timestamp: number | null): string {
  if (!timestamp) {
    return '-'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp * 1000))
}

/** 获取聊天类型标签（群聊/私聊） */
export function getChatTypeLabel(chat: ChatStream): string {
  return chat.chat_type === 'group' ? '群聊' : '私聊'
}

/** 获取聊天类型文本 */
export function getChatTypeText(chatType: ChatStreamType): string {
  return chatType === 'group' ? '群聊' : '私聊'
}

/** 获取聊天逻辑 ID（target_id 优先，回退 group_id/user_id） */
export function getChatLogicalId(chat: ChatStream): string {
  return chat.target_id || (chat.chat_type === 'group' ? chat.group_id : chat.user_id) || '-'
}

/** 获取目标规则类型（private 优先，否则 group） */
export function getTargetRuleType(target: TargetItem): ChatStreamType {
  return target.rule_type === 'private' || target.type === 'private' ? 'private' : 'group'
}

/** 规范化目标项（从 unknown 提取 TargetItem） */
export function normalizeTarget(target: unknown): TargetItem | null {
  if (!target || typeof target !== 'object') {
    return null
  }
  const rawTarget = target as Record<string, unknown>
  const platform = String(rawTarget.platform ?? '').trim()
  const itemId = String(rawTarget.item_id ?? '').trim()
  const rawRuleType = rawTarget.rule_type ?? rawTarget.type
  const ruleType = rawRuleType === 'private' ? 'private' : 'group'
  if (!platform || !itemId) {
    return null
  }
  return { platform, item_id: itemId, rule_type: ruleType }
}

/** 规范化互组列表 */
export function normalizeMutualGroups(value: unknown): ChatStreamGroupConfig[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((group) => {
    if (!group || typeof group !== 'object') {
      return { targets: [] }
    }
    const rawGroup = group as ChatStreamGroupConfig
    const rawTargets =
      rawGroup.targets ?? rawGroup.expression_groups ?? rawGroup.jargon_groups ?? []
    const targets = Array.isArray(rawTargets)
      ? rawTargets.map(normalizeTarget).filter((target): target is TargetItem => target !== null)
      : []
    return { targets }
  })
}

/** 序列化互组列表（清理为后端期望格式） */
export function serializeMutualGroups(groups: ChatStreamGroupConfig[]): ChatStreamGroupConfig[] {
  return groups.map((group) => ({
    targets: (group.targets ?? []).map((target) => ({
      platform: target.platform,
      item_id: target.item_id,
      rule_type: getTargetRuleType(target),
    })),
  }))
}

/** 目标唯一键 */
export function targetKey(target: TargetItem): string {
  return `${target.platform}:${target.item_id}:${getTargetRuleType(target)}`
}

/** 目标标签（含类型文本） */
export function targetLabel(target: TargetItem): string {
  return `${target.platform}:${target.item_id}:${getChatTypeText(getTargetRuleType(target))}`
}

/** 获取目标显示名（从映射表查找，找不到返回"未找到聊天流"） */
export function getTargetDisplayName(
  target: TargetItem,
  chatNameByTargetKey: Map<string, string>
): string {
  return chatNameByTargetKey.get(targetKey(target)) ?? '未找到聊天流'
}

/** 聊天流转目标项 */
export function chatToTarget(chat: ChatStream): TargetItem {
  return {
    platform: chat.platform,
    item_id: getChatLogicalId(chat),
    rule_type: chat.chat_type,
  }
}

/** 匹配搜索（12 字段模糊匹配） */
export function matchesSearch(chat: ChatStream, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase()
  if (!normalizedQuery) {
    return true
  }

  return [
    chat.id,
    chat.display_name,
    chat.session_id,
    chat.chat_type,
    chat.target_id,
    chat.platform,
    chat.group_id,
    chat.group_name,
    chat.user_id,
    chat.user_nickname,
    chat.user_cardname,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(normalizedQuery))
}

/** 匹配类型筛选 */
export function matchesTypeFilter(chat: ChatStream, filter: ChatTypeFilter): boolean {
  return filter === 'all' || chat.chat_type === filter
}

/** 格式化规则目标描述 */
export function formatRuleTarget(rule: ChatConfigRule | null): string {
  if (!rule) {
    return '未命中显式规则，使用默认行为'
  }
  if (rule.is_default) {
    return '默认规则'
  }
  const platform = rule.platform || '*'
  const itemId = rule.item_id || '*'
  return `${platform}:${itemId}:${getChatTypeText(rule.type === 'private' ? 'private' : 'group')}`
}