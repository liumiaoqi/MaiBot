/**
 * 智能体管理 API
 *
 * 请求样板（认证、解析、错误格式化）由 @/lib/http 的请求客户端承担；
 * 本文件只声明 endpoint、业务错误文案与响应体 success 标记的解包规则。
 */
import { backendApi, requireSuccess } from '@/lib/http'

const API_BASE = '/api/webui/agent'

export interface InternalRelationship {
  target_agent_id: string
  relationship_type: string
  attitude: string
  interaction_style: string
  mention_tendency: number
  anti_mechanization: string
}

export interface AgentConfigInfo {
  agent_id: string
  display_name: string
  personality: string
  reply_style: string
  is_default: boolean
  color: string
  emotion_baseline: Record<string, number>
  emotion_decay_rate: number
  relationship_growth_rate: number
  talk_value_modifier: number
  idle_backoff_modifier: number
  memory_focus_areas: string[]
  internal_relationships: InternalRelationship[]
  anti_mechanization_rules: string[]
}

export interface EmotionStateInfo {
  agent_id: string
  emotions: Record<string, number>
  dominant_emotion: string
  dominant_emotion_label: string
  emotion_labels: Record<string, string>
}

export interface RelationshipInfo {
  user_id: string
  level: number
  level_name: string
  score: number
  total_interactions: number
}

export interface SessionAgentInfo {
  session_id: string
  display_name: string
  agent_id: string
  agent_display_name: string
}

interface AgentListResponse {
  success: boolean
  total: number
  data: AgentConfigInfo[]
}

interface AgentDetailResponse {
  success: boolean
  data: AgentConfigInfo
}

interface EmotionStateResponse {
  success: boolean
  agent_id: string
  emotions: Record<string, number>
  dominant_emotion: string
  dominant_emotion_label: string
  emotion_labels: Record<string, string>
}

interface RelationshipSummaryResponse {
  success: boolean
  agent_id: string
  relationships: RelationshipInfo[]
}

interface SessionBindingResponse {
  success: boolean
  session_id: string
  agent_id: string | null
  display_name: string | null
}

interface GroupBindingResponse {
  success: boolean
  group_id: string
  agent_id: string
  display_name: string | null
}

interface GroupBindingsListResponse {
  success: boolean
  bindings: Record<string, string>
}

interface SessionsByAgentResponse {
  success: boolean
  agent_id: string
  sessions: SessionAgentInfo[]
}

interface ReloadResponse {
  success: boolean
  message: string
  total: number
}

export async function getAgentList(): Promise<AgentConfigInfo[]> {
  const data = await backendApi.get<AgentListResponse>(`${API_BASE}/list`, {
    errorMessage: '获取智能体列表失败',
  })
  const checked = requireSuccess(data, '获取智能体列表失败')
  return checked.data
}

export async function getAgentDetail(agentId: string): Promise<AgentConfigInfo> {
  const data = await backendApi.get<AgentDetailResponse>(`${API_BASE}/${encodeURIComponent(agentId)}`, {
    errorMessage: '获取智能体详情失败',
  })
  return requireSuccess(data, '获取智能体详情失败').data
}

export async function getAgentEmotion(agentId: string): Promise<EmotionStateInfo> {
  const data = await backendApi.get<EmotionStateResponse>(`${API_BASE}/emotion/${encodeURIComponent(agentId)}`, {
    errorMessage: '获取智能体情绪状态失败',
  })
  const checked = requireSuccess(data, '获取智能体情绪状态失败')
  return {
    agent_id: checked.agent_id,
    emotions: checked.emotions,
    dominant_emotion: checked.dominant_emotion,
    dominant_emotion_label: checked.dominant_emotion_label,
    emotion_labels: checked.emotion_labels,
  }
}

export async function getAgentRelationships(agentId: string): Promise<RelationshipInfo[]> {
  const data = await backendApi.get<RelationshipSummaryResponse>(
    `${API_BASE}/relationship/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取智能体关系概览失败' }
  )
  const checked = requireSuccess(data, '获取智能体关系概览失败')
  return checked.relationships
}

export async function getSessionBinding(sessionId: string): Promise<SessionBindingResponse> {
  const data = await backendApi.get<SessionBindingResponse>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}`,
    { errorMessage: '获取会话绑定失败' }
  )
  return requireSuccess(data, '获取会话绑定失败')
}

export async function bindSessionAgent(
  sessionId: string,
  agentId: string
): Promise<SessionBindingResponse> {
  const data = await backendApi.put<SessionBindingResponse>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}`,
    { body: { agent_id: agentId }, errorMessage: '绑定会话智能体失败' }
  )
  return requireSuccess(data, '绑定会话智能体失败')
}

export async function unbindSessionAgent(sessionId: string): Promise<void> {
  const data = await backendApi.delete<SessionBindingResponse>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}`,
    { errorMessage: '解除会话绑定失败' }
  )
  requireSuccess(data, '解除会话绑定失败')
}

export async function getGroupBindings(): Promise<Record<string, string>> {
  const data = await backendApi.get<GroupBindingsListResponse>(`${API_BASE}/binding/group`, {
    errorMessage: '获取群绑定列表失败',
  })
  return requireSuccess(data, '获取群绑定列表失败').bindings
}

export async function bindGroupAgent(
  groupId: string,
  agentId: string
): Promise<GroupBindingResponse> {
  const data = await backendApi.put<GroupBindingResponse>(`${API_BASE}/binding/group`, {
    body: { group_id: groupId, agent_id: agentId },
    errorMessage: '绑定群智能体失败',
  })
  return requireSuccess(data, '绑定群智能体失败')
}

export async function unbindGroupAgent(groupId: string): Promise<void> {
  const data = await backendApi.delete<GroupBindingResponse>(
    `${API_BASE}/binding/group/${encodeURIComponent(groupId)}`,
    { errorMessage: '解除群绑定失败' }
  )
  requireSuccess(data, '解除群绑定失败')
}

export async function getSessionsByAgent(agentId: string): Promise<SessionAgentInfo[]> {
  const data = await backendApi.get<SessionsByAgentResponse>(
    `${API_BASE}/sessions/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取智能体会话列表失败' }
  )
  return requireSuccess(data, '获取智能体会话列表失败').sessions
}

export async function reloadAgents(): Promise<{ message: string; total: number }> {
  const data = await backendApi.post<ReloadResponse>(`${API_BASE}/reload`, {
    errorMessage: '重新加载智能体配置失败',
  })
  const checked = requireSuccess(data, '重新加载智能体配置失败')
  return { message: checked.message, total: checked.total }
}

// ========== 子智能体监控 API ==========

export interface SubAgentRecord {
  id: number
  subagent_id: string
  agent_id: string
  subagent_type: string
  session_id: string | null
  lifecycle: string
  status: string
  trigger_type: string
  trigger_reason: string
  fork_context_captured: boolean
  input_tokens: number
  output_tokens: number
  cache_hit_tokens: number
  started_at: string | null
  completed_at: string | null
  error_message: string
  result_summary: string
}

export interface SubAgentStats {
  total_executions: number
  by_type: Record<string, number>
  by_status: Record<string, number>
  total_input_tokens: number
  total_output_tokens: number
  total_cache_hit_tokens: number
}

interface SubAgentListResponse {
  success: boolean
  total: number
  data: SubAgentRecord[]
}

interface SubAgentStatsResponse {
  success: boolean
  total_executions: number
  by_type: Record<string, number>
  by_status: Record<string, number>
  total_input_tokens: number
  total_output_tokens: number
  total_cache_hit_tokens: number
}

export async function getSubAgentRecords(params?: {
  agent_id?: string
  subagent_type?: string
  status?: string
  limit?: number
}): Promise<SubAgentRecord[]> {
  const data = await backendApi.get<SubAgentListResponse>(`${API_BASE}/subagent/records`, {
    query: {
      agent_id: params?.agent_id || undefined,
      subagent_type: params?.subagent_type || undefined,
      status: params?.status || undefined,
      limit: params?.limit || undefined,
    },
    errorMessage: '获取子智能体记录失败',
  })
  const checked = requireSuccess(data, '获取子智能体记录失败')
  return checked.data
}

export async function getSubAgentStats(): Promise<SubAgentStats> {
  const data = await backendApi.get<SubAgentStatsResponse>(`${API_BASE}/subagent/stats`, {
    errorMessage: '获取子智能体统计失败',
  })
  const checked = requireSuccess(data, '获取子智能体统计失败')
  return {
    total_executions: checked.total_executions,
    by_type: checked.by_type,
    by_status: checked.by_status,
    total_input_tokens: checked.total_input_tokens,
    total_output_tokens: checked.total_output_tokens,
    total_cache_hit_tokens: checked.total_cache_hit_tokens,
  }
}

export interface AgentIndicatorInfo {
  agent_id: string
  display_name: string
  color: string
}

export interface AgentStatsInfo {
  total_agents: number
  active_agents: number
  total_active_sessions: number
}

export interface BatchBindItem {
  session_id: string
  agent_id: string
}

export interface BatchBindError {
  session_id: string
  error: string
}

export interface BatchBindResponse {
  success: boolean
  total: number
  succeeded: number
  failed: number
  errors: BatchBindError[]
}

export async function batchBindSessions(bindings: BatchBindItem[]): Promise<BatchBindResponse> {
  return backendApi.put<BatchBindResponse>(`${API_BASE}/binding/batch`, {
    body: { bindings },
    errorMessage: '批量绑定智能体失败',
  })
}