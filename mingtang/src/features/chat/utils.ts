/**
 * 聊天域工具函数
 *
 * localStorage 工具从 dashboard routes/chat/utils.ts 搬移适配；
 * resolveStatusKind / matchesMonitorTarget / deduplicateMessage 为
 * 从 dashboard index.tsx 内联逻辑提取的纯函数（REQ-R3-04 / 消息去重）。
 */
import type { ChatRuntimeStatus, ChatTab, MonitorTargetCandidate, SavedVirtualTab } from './types'

import { VIRTUAL_TABS_STORAGE_KEY } from './types'

// ─── localStorage 工具 ───────────────────────────────────────────

// 生成唯一用户 ID
export function generateUserId(): string {
  return 'webui_' + Math.random().toString(36).slice(2, 11) + '_' + Date.now().toString(36)
}

// 从 localStorage 获取或生成用户 ID
export function getOrCreateUserId(): string {
  const storageKey = 'maibot_webui_user_id'
  let userId = localStorage.getItem(storageKey)
  if (!userId) {
    userId = generateUserId()
    localStorage.setItem(storageKey, userId)
  }
  return userId
}

// 从 localStorage 获取用户昵称
export function getStoredUserName(): string {
  return localStorage.getItem('maibot_webui_user_name') || 'WebUI用户'
}

// 保存用户昵称到 localStorage
export function saveUserName(name: string): void {
  localStorage.setItem('maibot_webui_user_name', name)
}

// 从 localStorage 获取保存的虚拟标签页
export function getSavedVirtualTabs(): SavedVirtualTab[] {
  try {
    const saved = localStorage.getItem(VIRTUAL_TABS_STORAGE_KEY)
    if (saved) {
      return JSON.parse(saved)
    }
  } catch (e) {
    console.error('[Chat] 加载虚拟标签页失败:', e)
  }
  return []
}

// 保存虚拟标签页到 localStorage
export function saveVirtualTabs(tabs: SavedVirtualTab[]): void {
  try {
    localStorage.setItem(VIRTUAL_TABS_STORAGE_KEY, JSON.stringify(tabs))
  } catch (e) {
    console.error('[Chat] 保存虚拟标签页失败:', e)
  }
}

// 本地聊天会话对用户来说就是和 bot 对话，不展示内部 WebUI 占位名。
export function getChatTabDisplayName(tab: ChatTab, botNameFallback: string): string {
  if (tab.type === 'virtual') {
    return tab.label
  }
  return tab.sessionInfo.bot_name?.trim() || botNameFallback
}

// ─── 运行状态推断（REQ-R3-04）─────────────────────────────────────

/**
 * 按 stage / detail 关键词推断运行状态种类。
 * 优先级：error > thinking > typing > acting > idle
 */
export function resolveStatusKind(stage: string, detail: string = ''): ChatRuntimeStatus {
  const s = stage.toLowerCase()
  const d = detail.toLowerCase()
  if (s.includes('error') || s.includes('fail') || d.includes('error') || d.includes('fail')) {
    return 'error'
  }
  if (s.includes('think') || s.includes('reason')) {
    return 'thinking'
  }
  if (s.includes('typ') || s.includes('generat') || s.includes('writ')) {
    return 'typing'
  }
  if (s.includes('act') || s.includes('tool') || s.includes('execut') || s.includes('action')) {
    return 'acting'
  }
  return 'idle'
}

// ─── 监控事件三级匹配（REQ-R3-04）────────────────────────────────

/**
 * 判断监控事件是否属于某个聊天标签页。
 * 三级匹配：session_id 精确 > session_name 匹配 label > platform 匹配虚拟配置。
 */
export function matchesMonitorTarget(event: MonitorTargetCandidate, tab: ChatTab): boolean {
  // 一级：session_id 精确匹配
  if (
    event.session_id &&
    tab.sessionInfo.session_id &&
    event.session_id === tab.sessionInfo.session_id
  ) {
    return true
  }
  // 二级：session_name 匹配 label
  if (event.session_name && event.session_name === tab.label) {
    return true
  }
  // 三级：platform 匹配 virtualConfig.platform
  if (
    event.platform &&
    tab.virtualConfig?.platform &&
    event.platform === tab.virtualConfig.platform
  ) {
    return true
  }
  return false
}

// ─── 消息去重（hash 上限 100——REQ-R3-01 消息去重）──────────────

/**
 * 消息去重纯函数：判断 hash 是否重复，并在加入后维持上限。
 * 上限淘汰策略：超过 limit 时删除最早插入的 hash（Set 保持插入顺序）。
 */
export function deduplicateMessage(
  processedSet: Set<string>,
  hash: string,
  limit: number = 100
): { isDuplicate: boolean; updatedSet: Set<string> } {
  if (processedSet.has(hash)) {
    return { isDuplicate: true, updatedSet: processedSet }
  }
  const updatedSet = new Set(processedSet)
  updatedSet.add(hash)
  if (updatedSet.size > limit) {
    const firstKey = updatedSet.values().next().value
    if (firstKey) updatedSet.delete(firstKey)
  }
  return { isDuplicate: false, updatedSet }
}