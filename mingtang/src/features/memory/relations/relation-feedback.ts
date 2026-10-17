import { backendApi } from '@/lib/http'

/**
 * 关系真值回路（0004）的前端局部契约——**手写，不抄后端 schema**。
 *
 * ⚠️ 请求体**恰好 4 键**：后端 `V5ActionRequest` 是 `extra='forbid'`，
 * 多发一个键（例如把 v5 通用的 `strength` 也带上）会直接 **422**。
 * ⚠️ `decision` 是**人的显式判断**，只认 `raise / lower / neutral`；
 * 留空由后端具名拒绝（不静默当 `neutral`）——前端也在提交前拦一道。
 */
export type RelationFeedbackDecision = 'raise' | 'lower' | 'neutral'

/** 请求体（4 键，别加） */
export interface RelationFeedbackRequest {
  target: string
  decision: RelationFeedbackDecision
  reason: string
  updated_by: string
}

/** 后端返回（`v5_memory.record_relation_feedback` 的字段） */
export interface RelationFeedbackResult {
  success: boolean
  error?: string
  relation_hash?: string
  action?: RelationFeedbackDecision
  delta?: number
  confidence_after?: number
  event_id?: number
}

const FEEDBACK_PATH = '/api/webui/memory/relations/feedback'

/** 提交一次显式判断：改 confidence（±0.1）+ 写账本（`relation_feedback_events`） */
export function submitRelationFeedback(
  request: RelationFeedbackRequest
): Promise<RelationFeedbackResult> {
  return backendApi.post<RelationFeedbackResult>(FEEDBACK_PATH, { body: request })
}
