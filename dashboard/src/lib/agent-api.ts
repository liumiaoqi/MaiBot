/**
 * 智能体管理 API
 *
 * 请求样板（认证、解析、错误格式化、ApiResponse 自动解包）由 @/lib/http 的请求客户端承担；
 * 本文件只声明 endpoint 与业务错误文案。
 */
import { backendApi } from '@/lib/http'

const API_BASE = '/api/webui/agents'

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

export interface CohabitantInfo {
  agent_id: string
  display_name: string
  is_primary: boolean
  status: 'active' | 'standby' | 'dormant' | 'bound_inactive'
  vitality_value?: number
}

export interface SessionAgentInfo {
  session_id: string
  display_name: string
  agent_id: string
  agent_display_name: string
  status: 'active' | 'standby' | 'dormant' | 'bound_inactive'
  is_primary: boolean
  last_spoke_at: string | null
  cohabitants: CohabitantInfo[]
  vitality_value?: number
}

interface AgentListData {
  total: number
  data: AgentConfigInfo[]
}

interface SessionBindingData {
  session_id: string
  agent_id: string | null
  display_name: string | null
}

interface GroupBindingData {
  group_id: string
  agent_id: string
  display_name: string | null
}

interface GroupBindingsListData {
  bindings: Record<string, string>
}

interface SessionsByAgentData {
  agent_id: string
  sessions: SessionAgentInfo[]
}

interface ReloadData {
  message: string
  total: number
}

export async function getAgentList(): Promise<AgentConfigInfo[]> {
  const data = await backendApi.get<AgentListData>(`${API_BASE}/list`, {
    errorMessage: '获取智能体列表失败',
  })
  return data.data
}

interface AgentDetailData {
  success: boolean
  data: AgentConfigInfo
}

export async function getAgentDetail(agentId: string): Promise<AgentConfigInfo> {
  const data = await backendApi.get<AgentDetailData>(`${API_BASE}/${encodeURIComponent(agentId)}`, {
    errorMessage: '获取智能体详情失败',
  })
  return data.data
}

export async function getAgentEmotion(agentId: string): Promise<EmotionStateInfo> {
  return backendApi.get<EmotionStateInfo>(`${API_BASE}/emotion/${encodeURIComponent(agentId)}`, {
    errorMessage: '获取智能体情绪状态失败',
  })
}

export async function getAgentRelationships(agentId: string): Promise<RelationshipInfo[]> {
  const data = await backendApi.get<RelationshipSummaryData>(
    `${API_BASE}/relationship/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取智能体关系概览失败' }
  )
  return data.relationships
}

interface RelationshipSummaryData {
  agent_id: string
  relationships: RelationshipInfo[]
}

export async function getSessionBinding(sessionId: string): Promise<SessionBindingData> {
  return backendApi.get<SessionBindingData>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}`,
    { errorMessage: '获取会话绑定失败' }
  )
}

export async function bindSessionAgent(
  sessionId: string,
  agentId: string
): Promise<SessionBindingData> {
  return backendApi.put<SessionBindingData>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}`,
    { body: { agent_id: agentId }, errorMessage: '绑定会话智能体失败' }
  )
}

export async function unbindSessionAgent(sessionId: string): Promise<void> {
  await backendApi.delete<unknown>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}`,
    { errorMessage: '解除会话绑定失败' }
  )
}

export async function unbindSessionSpecificAgent(
  sessionId: string,
  agentId: string
): Promise<void> {
  await backendApi.delete<unknown>(
    `${API_BASE}/binding/session/${encodeURIComponent(sessionId)}/${encodeURIComponent(agentId)}`,
    { errorMessage: '解除指定智能体绑定失败' }
  )
}

export async function getGroupBindings(): Promise<Record<string, string>> {
  const data = await backendApi.get<GroupBindingsListData>(`${API_BASE}/binding/group`, {
    errorMessage: '获取群绑定列表失败',
  })
  return data.bindings
}

export async function bindGroupAgent(
  groupId: string,
  agentId: string
): Promise<GroupBindingData> {
  return backendApi.put<GroupBindingData>(`${API_BASE}/binding/group`, {
    body: { group_id: groupId, agent_id: agentId },
    errorMessage: '绑定群智能体失败',
  })
}

export async function unbindGroupAgent(groupId: string): Promise<void> {
  await backendApi.delete<unknown>(
    `${API_BASE}/binding/group/${encodeURIComponent(groupId)}`,
    { errorMessage: '解除群绑定失败' }
  )
}

export async function getSessionsByAgent(agentId: string): Promise<SessionAgentInfo[]> {
  const data = await backendApi.get<SessionsByAgentData>(
    `${API_BASE}/sessions/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取智能体会话列表失败' }
  )
  return data.sessions
}

export async function reloadAgents(): Promise<{ message: string; total: number }> {
  return backendApi.post<ReloadData>(`${API_BASE}/reload`, {
    errorMessage: '重新加载智能体配置失败',
  })
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

interface SubAgentListData {
  total: number
  data: SubAgentRecord[]
}

export async function getSubAgentRecords(params?: {
  agent_id?: string
  subagent_type?: string
  status?: string
  limit?: number
}): Promise<SubAgentRecord[]> {
  const data = await backendApi.get<SubAgentListData>(`${API_BASE}/subagent/records`, {
    query: {
      agent_id: params?.agent_id || undefined,
      subagent_type: params?.subagent_type || undefined,
      status: params?.status || undefined,
      limit: params?.limit || undefined,
    },
    errorMessage: '获取子智能体记录失败',
  })
  return data.data
}

export async function getSubAgentStats(): Promise<SubAgentStats> {
  return backendApi.get<SubAgentStats>(`${API_BASE}/subagent/stats`, {
    errorMessage: '获取子智能体统计失败',
  })
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

export interface BatchBindResult {
  total: number
  succeeded: number
  failed: number
  errors: BatchBindError[]
}

export async function batchBindSessions(bindings: BatchBindItem[]): Promise<BatchBindResult> {
  return backendApi.put<BatchBindResult>(`${API_BASE}/binding/batch`, {
    body: { bindings },
    errorMessage: '批量绑定智能体失败',
  })
}

// ========== 批量查询 API ==========

export interface BatchEmotionItem {
  emotions: Record<string, number>
  dominant_emotion: string
  dominant_emotion_label: string
  emotion_labels: Record<string, string>
}

export interface BatchRelationshipItem {
  user_id: string
  level: number
  level_name: string
  score: number
  total_interactions: number
}

export interface BatchLatestSubAgentItem {
  id: number
  subagent_id: string
  agent_id: string
  subagent_type: string
  status: string
  completed_at: string | null
  result_summary: string
}

export interface EmotionBehaviorRule {
  emotion_type: string
  intensity_threshold: number
  behavior_tendency: string
  reply_style_modifier: string
}

export async function getBatchEmotions(): Promise<Record<string, BatchEmotionItem>> {
  const data = await backendApi.get<{ data: Record<string, BatchEmotionItem> }>(`${API_BASE}/batch/emotion`, {
    errorMessage: '批量获取情绪状态失败',
  })
  return data.data
}

export async function getBatchRelationships(): Promise<Record<string, BatchRelationshipItem[]>> {
  const data = await backendApi.get<{ data: Record<string, BatchRelationshipItem[]> }>(`${API_BASE}/batch/relationships`, {
    errorMessage: '批量获取关系概览失败',
  })
  return data.data
}

export async function getBatchSessionCounts(): Promise<Record<string, number>> {
  const data = await backendApi.get<{ data: Record<string, number> }>(`${API_BASE}/batch/sessions`, {
    errorMessage: '批量获取会话数量失败',
  })
  return data.data
}

export async function getBatchLatestSubAgentRecords(): Promise<Record<string, BatchLatestSubAgentItem | null>> {
  const data = await backendApi.get<{ data: Record<string, BatchLatestSubAgentItem | null> }>(`${API_BASE}/batch/subagent-latest`, {
    errorMessage: '批量获取子智能体记录失败',
  })
  return data.data
}

export async function getEmotionBehaviorRules(agentId: string): Promise<EmotionBehaviorRule[]> {
  const data = await backendApi.get<{ agent_id: string; rules: EmotionBehaviorRule[] }>(
    `${API_BASE}/emotion-behavior-rules/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取情绪-行为映射规则失败' }
  )
  return data.rules
}

// ---- 交互活化 API ----

export interface InteractionEventResponse {
  event_id: string
  initiator_agent_id: string
  target_agent_id: string
  interaction_type: string
  trigger_reason: string
  content_summary: string
  emotion_effects: string
  relationship_effect: number
  memory_write_status: string
  echo_depth: number
  echo_parent_event_id: string
  metadata: string
  created_at: string | null
}

export interface InnerMonologueEventResponse {
  monologue_id: string
  agent_id: string
  emotion_snapshot: string
  content: string
  self_emotion_effect: string
  memory_references: string
  created_at: string | null
}

export interface AgentProfileResponse {
  observer_agent_id: string
  target_agent_id: string
  summary: string
  traits: string[]
  interaction_count: number
  emotion_tendency: string
  refresh_status: string
}

export interface InteractionHistoryParams {
  agent_id?: string
  target_agent_id?: string
  interaction_type?: string
  time_start?: string
  time_end?: string
  limit?: number
  offset?: number
}

export interface InteractionConfigResponse {
  enabled: boolean
  cooldown_minutes: number
  max_interactions_per_hour: number
  max_interactions_per_day: number
  echo_enabled: boolean
  echo_max_depth: number
  echo_decay_ratio: number
  monologue_enabled: boolean
  monologue_min_interval_minutes: number
  monologue_idle_threshold_minutes: number
  monologue_emotion_intensity_threshold: number
}

export async function getRecentInteractions(limit = 20): Promise<InteractionEventResponse[]> {
  return backendApi.get<InteractionEventResponse[]>(
    `${API_BASE}/interactions/recent?limit=${limit}`,
    { errorMessage: '获取最近交互事件失败' }
  )
}

export async function getInteractionDetail(eventId: string): Promise<InteractionEventResponse> {
  return backendApi.get<InteractionEventResponse>(
    `${API_BASE}/interactions/${encodeURIComponent(eventId)}`,
    { errorMessage: '获取交互事件详情失败' }
  )
}

export async function getInteractionHistory(
  params: InteractionHistoryParams = {}
): Promise<InteractionEventResponse[]> {
  const query = new URLSearchParams()
  if (params.agent_id) query.set('agent_id', params.agent_id)
  if (params.target_agent_id) query.set('target_agent_id', params.target_agent_id)
  if (params.interaction_type) query.set('interaction_type', params.interaction_type)
  if (params.time_start) query.set('time_start', params.time_start)
  if (params.time_end) query.set('time_end', params.time_end)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.offset) query.set('offset', String(params.offset))
  const qs = query.toString()
  return backendApi.get<InteractionEventResponse[]>(
    `${API_BASE}/interactions/history${qs ? `?${qs}` : ''}`,
    { errorMessage: '获取交互历史失败' }
  )
}

export async function getAgentMonologues(
  agentId: string,
  limit = 10
): Promise<InnerMonologueEventResponse[]> {
  return backendApi.get<InnerMonologueEventResponse[]>(
    `${API_BASE}/monologue/${encodeURIComponent(agentId)}?limit=${limit}`,
    { errorMessage: '获取内心独白失败' }
  )
}

export async function getAgentProfile(
  observerId: string,
  targetId: string
): Promise<AgentProfileResponse> {
  return backendApi.get<AgentProfileResponse>(
    `${API_BASE}/profile/${encodeURIComponent(observerId)}/${encodeURIComponent(targetId)}`,
    { errorMessage: '获取智能体画像失败' }
  )
}

export async function getInteractionConfig(): Promise<InteractionConfigResponse> {
  return backendApi.get<InteractionConfigResponse>(
    `${API_BASE}/interactions/config`,
    { errorMessage: '获取交互配置失败' }
  )
}

export async function manualTriggerInteraction(req: {
  initiator_id: string
  target_id: string
  interaction_type: string
  reason: string
}): Promise<{ event_id: string; error: string }> {
  return backendApi.post<{ event_id: string; error: string }>(
    `${API_BASE}/interactions/trigger`,
    { body: req, errorMessage: '手动触发交互失败' }
  )
}

export async function getInteractionHotspots(): Promise<{ pair: string; count: number }[]> {
  const data = await backendApi.get<{ hotspots: { pair: string; count: number }[] }>(
    `${API_BASE}/interactions/hotspots`,
    { errorMessage: '获取交互热点失败' }
  )
  return data.hotspots ?? []
}

// ========== 智能体自主性 API ==========

export interface ActiveAgentItem {
  agent_id: string
  is_primary: boolean
  activation_reason: string
  activated_at: string | null
  last_spoke_at: string | null
}

export interface BehaviorIntentItem {
  intent_id: string
  agent_id: string
  intent_type: string
  intent_strength: number
  intent_source: string
  source_description: string
  status: string
  created_at: string | null
}

export interface InterjectionEventItem {
  event_id: string
  agent_id: string
  primary_agent_id: string
  interjection_type: string
  trigger_reason: string
  intent_strength: number
  content_summary: string
  created_at: string | null
}

export interface SpeakerChangeItem {
  record_id: string
  from_agent_id: string
  to_agent_id: string
  change_type: string
  change_reason: string
  created_at: string | null
}

interface PrimaryAgentData {
  session_id: string
  agent_id: string | null
  activation_reason: string
  activated_at: string | null
}

interface SwitchSpeakerData {
  session_id: string
  from_agent_id: string
  to_agent_id: string
}

interface TriggerInterjectionData {
  session_id: string
  agent_id: string
  error: string
}

export async function getActiveAgents(sessionId: string): Promise<ActiveAgentItem[]> {
  const data = await backendApi.get<{ session_id: string; data: ActiveAgentItem[] }>(
    `${API_BASE}/autonomy/active/${encodeURIComponent(sessionId)}`,
    { errorMessage: '获取活跃智能体列表失败' }
  )
  return data.data
}

export async function getPrimaryAgent(sessionId: string): Promise<PrimaryAgentData> {
  return backendApi.get<PrimaryAgentData>(
    `${API_BASE}/autonomy/primary/${encodeURIComponent(sessionId)}`,
    { errorMessage: '获取主发言智能体失败' }
  )
}

export async function switchSpeaker(
  sessionId: string,
  targetAgentId: string,
  reason = 'manual_switch'
): Promise<SwitchSpeakerData> {
  return backendApi.post<SwitchSpeakerData>(
    `${API_BASE}/autonomy/switch-speaker`,
    { body: { session_id: sessionId, target_agent_id: targetAgentId, reason }, errorMessage: '切换主发言智能体失败' }
  )
}

export async function triggerInterjection(
  sessionId: string,
  agentId: string,
  reason = 'manual_trigger'
): Promise<TriggerInterjectionData> {
  return backendApi.post<TriggerInterjectionData>(
    `${API_BASE}/autonomy/trigger-interjection`,
    { body: { session_id: sessionId, agent_id: agentId, reason }, errorMessage: '手动触发插话失败' }
  )
}

export async function getBehaviorIntents(sessionId: string, limit = 50): Promise<BehaviorIntentItem[]> {
  const data = await backendApi.get<{ session_id: string; data: BehaviorIntentItem[] }>(
    `${API_BASE}/autonomy/intents/${encodeURIComponent(sessionId)}?limit=${limit}`,
    { errorMessage: '获取行为意图列表失败' }
  )
  return data.data
}

export async function getInterjectionEvents(sessionId: string, limit = 50): Promise<InterjectionEventItem[]> {
  const data = await backendApi.get<{ session_id: string; data: InterjectionEventItem[] }>(
    `${API_BASE}/autonomy/interjection-events/${encodeURIComponent(sessionId)}?limit=${limit}`,
    { errorMessage: '获取插话事件列表失败' }
  )
  return data.data
}

export async function getSpeakerChanges(sessionId: string, limit = 50): Promise<SpeakerChangeItem[]> {
  const data = await backendApi.get<{ session_id: string; data: SpeakerChangeItem[] }>(
    `${API_BASE}/autonomy/speaker-changes/${encodeURIComponent(sessionId)}?limit=${limit}`,
    { errorMessage: '获取发言权变更记录失败' }
  )
  return data.data
}

export interface AutonomyLogItem {
  agent_id: string
  event_type: string
  detail: string
  timestamp: string
  session_id: string
  log_level: string
}

export interface AutonomyLogResponse {
  items: AutonomyLogItem[]
  total: number
  page: number
  page_size: number
}

export async function getAutonomyLogs(params?: {
  agent_id?: string
  event_type?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}): Promise<AutonomyLogResponse> {
  const searchParams = new URLSearchParams()
  if (params?.agent_id) searchParams.set('agent_id', params.agent_id)
  if (params?.event_type) searchParams.set('event_type', params.event_type)
  if (params?.start_time) searchParams.set('start_time', params.start_time)
  if (params?.end_time) searchParams.set('end_time', params.end_time)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))

  const query = searchParams.toString()
  return backendApi.get<AutonomyLogResponse>(
    `${API_BASE}/autonomy-logs${query ? `?${query}` : ''}`,
    { errorMessage: '获取自主性日志失败' }
  )
}

export interface VitalityAgentItem {
  agent_id: string
  display_name: string
  state: 'active' | 'standby' | 'dormant'
  vitality_value: number
  last_stimulus_at: string | null
}

interface SessionVitalityData {
  session_id: string
  active_agents: VitalityAgentItem[]
  standby_agents: VitalityAgentItem[]
  dormant_agents: VitalityAgentItem[]
}

export async function fetchSessionVitality(sessionId: string): Promise<SessionVitalityData> {
  return backendApi.get<SessionVitalityData>(
    `${API_BASE}/vitality?session_id=${encodeURIComponent(sessionId)}`,
    { errorMessage: '获取生命力状态失败' }
  )
}

export interface CohabitantEntryItem {
  agent_id: string
  display_name: string
  state: string
  vitality_level: string
  emotion_tendency: string
}

interface StateAwarenessData {
  session_id: string
  cohabitant_entries: CohabitantEntryItem[]
  summary_preview: string
  active_rules: Array<{ rule_name: string; active: boolean }>
}

export async function fetchStateAwareness(sessionId: string): Promise<StateAwarenessData> {
  return backendApi.get<StateAwarenessData>(
    `${API_BASE}/state-awareness?session_id=${encodeURIComponent(sessionId)}`,
    { errorMessage: '获取状态互知数据失败' }
  )
}
