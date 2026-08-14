/**
 * tabs/import/utils —— 导入面板专属渲染辅助（从旧 ImportTab 文件头迁出）。
 *
 * 与 knowledge-base/utils.ts 的分工：这里只放「导入创建/队列/详情」UI 层专属的
 * 格式化与检索辅助（聊天流选择器 + 分块摘要），通用导入工具仍在 ../utils。
 */
import type { MemoryImportChatTargetPayload } from '@/lib/memory-api'

export function formatChunkSummary(
  done: unknown,
  total: unknown,
  failed: unknown,
  cancelled: unknown = 0,
): string {
  const doneCount = Number(done ?? 0)
  const totalCount = Number(total ?? 0)
  const failedCount = Number(failed ?? 0)
  const cancelledCount = Number(cancelled ?? 0)
  const parts = [`成功 ${doneCount} / ${totalCount} 分块`]
  if (failedCount > 0) {
    parts.push(`失败 ${failedCount}`)
  }
  if (cancelledCount > 0) {
    parts.push(`取消 ${cancelledCount}`)
  }
  return parts.join(' · ')
}

function compactTextParts(parts: Array<string | null | undefined>): string[] {
  return parts.map((part) => String(part ?? '').trim()).filter(Boolean)
}

function getUserIdLabel(chat: MemoryImportChatTargetPayload): string {
  const userId = String(chat.user_id ?? '').trim()
  if (!userId) {
    return ''
  }

  const platform = String(chat.platform ?? '').trim().toLowerCase()
  if (platform === 'qq') {
    return `QQ ${userId}`
  }
  if (platform === 'wechat' || platform === 'wx') {
    return `微信 ${userId}`
  }
  return `用户 ID ${userId}`
}

export function getChatTargetMetaParts(chat: MemoryImportChatTargetPayload): string[] {
  return compactTextParts([
    chat.platform || '未知平台',
    chat.is_group ? '群聊' : '私聊',
    chat.group_id ? `群号 ${chat.group_id}` : '',
    getUserIdLabel(chat),
  ])
}

function getChatTargetSearchText(chat: MemoryImportChatTargetPayload): string {
  return compactTextParts([
    chat.chat_name,
    chat.platform,
    chat.group_id,
    chat.user_id,
    chat.account_id,
    chat.scope,
    chat.chat_id,
  ])
    .join(' ')
    .toLowerCase()
}

export function getChatTargetValueLabel(chat: MemoryImportChatTargetPayload | undefined): string {
  if (!chat) {
    return '不绑定聊天流'
  }
  const idLabel = chat.group_id || chat.user_id
  return idLabel ? `${chat.chat_name} · ${idLabel}` : chat.chat_name
}

export function filterChatTargets(
  targets: MemoryImportChatTargetPayload[],
  query: string,
): MemoryImportChatTargetPayload[] {
  const normalizedQuery = query.trim().toLowerCase()
  if (!normalizedQuery) {
    return targets.slice(0, 8)
  }
  return targets.filter((chat) => getChatTargetSearchText(chat).includes(normalizedQuery)).slice(0, 12)
}
