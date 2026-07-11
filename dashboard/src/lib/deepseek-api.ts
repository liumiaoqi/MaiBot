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

export async function getDeepSeekOverview(): Promise<DeepSeekOverviewInfo> {
  return await backendApi.get<DeepSeekOverviewInfo>(`${API_BASE}/overview`, {
    errorMessage: '获取DeepSeek概览失败',
  })
}

export async function getAgentBudget(agentId: string): Promise<TokenBudgetInfo> {
  return await backendApi.get<TokenBudgetInfo>(
    `${API_BASE}/budget/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取Token预算分配失败' }
  )
}

export async function getAgentCacheStats(agentId: string): Promise<CacheStatsInfo> {
  return await backendApi.get<CacheStatsInfo>(
    `${API_BASE}/cache/${encodeURIComponent(agentId)}`,
    { errorMessage: '获取前缀缓存统计失败' }
  )
}

export async function getBatchOverview(): Promise<BatchOverviewInfo> {
  return await backendApi.get<BatchOverviewInfo>(`${API_BASE}/batch/overview`, {
    errorMessage: '获取批处理概览失败',
  })
}

export async function getAgentCost(
  agentId: string,
  periodDays: number = 30
): Promise<AgentCostInfo> {
  return await backendApi.get<AgentCostInfo>(
    `${API_BASE}/cost/${encodeURIComponent(agentId)}`,
    { query: { period_days: periodDays }, errorMessage: '获取智能体成本统计失败' }
  )
}

export async function getMonthlyCostReport(): Promise<MonthlyReportInfo> {
  return await backendApi.get<MonthlyReportInfo>(`${API_BASE}/cost/report`, {
    errorMessage: '获取月度成本报告失败',
  })
}
