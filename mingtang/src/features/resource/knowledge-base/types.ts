/**
 * 记忆管理页面的内部类型定义（R4-2-1）
 *
 * 砍 correction/graph/timeline/episodes/profiles/maintenance（spec.md §5.6 不做清单）
 */

/**
 * 4 tab 联合类型（砍 correction/graph/timeline/episodes/profiles/maintenance）
 *
 * 对齐 dashboard 原版 MemoryConsoleTab——R4-2 仅保留 4 tabs
 */
export type KnowledgeBaseTab = 'import' | 'tuning' | 'delete' | 'feedback'

/**
 * 深链接状态（砍 correction 相关参数 ?plan_id/?person_id + graph/timeline/episodes/profiles/maintenance 参数）
 *
 * 对齐 dashboard 原版深链接——R4-2 砍到 4 参数（tab/taskId/operationId/source）
 * 砍：chatId/timeStart/timeEnd/episodeId/paragraphHash/personId/correctionPlanId/maintenanceTarget
 */
export interface KnowledgeBaseDeepLinkState {
  tab: KnowledgeBaseTab
  taskId?: number
  operationId?: string
  source?: string
}

/**
 * 4 tab 常量数组（运行时遍历用——砍 correction/graph/timeline/episodes/profiles/maintenance）
 */
export const KNOWLEDGE_BASE_TABS = [
  'import',
  'tuning',
  'delete',
  'feedback',
] as const satisfies readonly KnowledgeBaseTab[]