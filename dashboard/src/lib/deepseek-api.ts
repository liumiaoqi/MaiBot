/**
 * DeepSeek 优化面板 API
 */
import { backendApi } from '@/lib/http'

const API_BASE = '/api/webui/deepseek'

export interface TokenBudgetSegment {
  segment: string
  ratio: number
  token_limit: number
}

export interface TokenBudgetInfo {
  agent_id: string
  model_context_window: number
  segments: TokenBudgetSegment[]
}

export interface CacheStatsInfo {
  agent_id: string
  hit_tokens: number
  miss_tokens: number
  hit_rate: number
  prefix_cache_enabled: boolean
}

export interface BatchTaskSummary {
  task_id: string
  agent_id: string
  task_type: string
  status: string
  priority: string
  degraded_to_realtime: boolean
  created_at: number
}

export interface BatchOverviewInfo {
  api_available: boolean
  pending_count: number
  degraded_count: number
  recent_tasks: BatchTaskSummary[]
}

export interface AgentCostInfo {
  agent_id: string
  total_cost: number
  total_input_tokens: number
  total_output_tokens: number
  total_cache_hit_tokens: number
}

export interface MonthlyReportInfo {
  by_agent: Record<string, { cost: number; input_tokens: number; output_tokens: number }>
  by_task_type: Record<string, { cost: number; input_tokens: number; output_tokens: number }>
}

export interface DeepSeekOverviewInfo {
  total_agents: number
  agents_with_budget: number
  agents_with_cache: number
  batch_api_available: boolean
  total_cost_30d: number
  avg_cache_hit_rate: number
}

interface OverviewResponse {
  total_agents: number
  agents_with_budget: number
  agents_with_cache: number
  batch_api_available: boolean
  total_cost_30d: number
  avg_cache_hit_rate: number
}

interface BudgetResponse {
  agent_id: string
  model_context_window: number
  segments: TokenBudgetSegment[]
}

interface CacheResponse {
  agent_id: string
  hit_tokens: number
  miss_tokens: number
  hit_rate: number
  prefix_cache_enabled: boolean
}

interface BatchOverviewResponse {
  api_available: boolean
  pending_count: number
  degraded_count: number
  recent_tasks: BatchTaskSummary[]
}

interface CostResponse {
  agent_id: string
  total_cost: number
  total_input_tokens: number
  total_output_tokens: number
  total_cache_hit_tokens: number
}

interface ReportResponse {
  by_agent: Record<string, { cost: number; input_tokens: number; output_tokens: number }>
  by_task_type: Record<string, { cost: number; input_tokens: number; output_tokens: number }>
}

export async function getDeepSeekOverview(): Promise<DeepSeekOverviewInfo> {
  const data = await backendApi.get<OverviewResponse>(`${API_BASE}/overview`, {
    errorMessage: '获取DeepSeek概览失败',
  })
  const checked =
  return {
    total_agents: checked.total_agents,
    agents_with_budget: checked.agents_with_budget,
    agents_with_cache: checked.agents_with_cache,
    batch_api_available: checked.batch_api_available,
    total_cost_30d: checked.total_cost_30d,
    avg_cache_hit_rate: checked.avg_cache_hit_rate,
  }
}

export async function getAgentBudget(agentId: string): Promise<TokenBudgetInfo> {
  const data = await backendApi.get<BudgetResponse>(
    `${API_BASE}/budget/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取Token预算分配失败' }
  )
  const checked =
  return {
    agent_id: checked.agent_id,
    model_context_window: checked.model_context_window,
    segments: checked.segments,
  }
}

export async function getAgentCacheStats(agentId: string): Promise<CacheStatsInfo> {
  const data = await backendApi.get<CacheResponse>(
    `${API_BASE}/cache/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取前缀缓存统计失败' }
  )
  const checked =
  return {
    agent_id: checked.agent_id,
    hit_tokens: checked.hit_tokens,
    miss_tokens: checked.miss_tokens,
    hit_rate: checked.hit_rate,
    prefix_cache_enabled: checked.prefix_cache_enabled,
  }
}

export async function getBatchOverview(): Promise<BatchOverviewInfo> {
  const data = await backendApi.get<BatchOverviewResponse>(`${API_BASE}/batch/overview`, {
    errorMessage: '获取批处理概览失败',
  })
  const checked =
  return {
    api_available: checked.api_available,
    pending_count: checked.pending_count,
    degraded_count: checked.degraded_count,
    recent_tasks: checked.recent_tasks,
  }
}

export async function getAgentCost(
  agentId: string,
  periodDays: number = 30
): Promise<AgentCostInfo> {
  const data = await backendApi.get<CostResponse>(
    `${API_BASE}/cost/${encodeURIComponent(agentId)}`,
    { query: { period_days: periodDays }, errorMessage: '获取智能体成本统计失败' }
  )
  const checked =
  return {
    agent_id: checked.agent_id,
    total_cost: checked.total_cost,
    total_input_tokens: checked.total_input_tokens,
    total_output_tokens: checked.total_output_tokens,
    total_cache_hit_tokens: checked.total_cache_hit_tokens,
  }
}

export async function getMonthlyCostReport(): Promise<MonthlyReportInfo> {
  const data = await backendApi.get<ReportResponse>(`${API_BASE}/cost/report`, {
    errorMessage: '获取月度成本报告失败',
  })
  const checked =
  return {
    by_agent: checked.by_agent,
    by_task_type: checked.by_task_type,
  }
}