/**
 * 统计数据 API（statistics 端点封装——P2-C #2）
 *
 * 请求样板（认证、解析、错误格式化、ApiResponse 自动解包）由 @/lib/http 的请求客户端承担；
 * 本文件只声明 statistics 端点、响应类型与业务错误文案。
 *
 * 消费方：monitor 域 use-llm-stats（本批次）+ home 域 use-dashboard-data（P2-D 组切换）。
 * 类型从两个既有消费文件提取签名后统一收敛于此。
 */
import { backendApi } from '@/lib/http'

/** 仪表盘摘要 */
export interface DashboardSummary {
  total_requests: number
  total_cost: number
  total_tokens: number
  online_time: number
  total_messages: number
  total_replies: number
  avg_response_time: number
  cost_per_hour: number
  tokens_per_hour: number
}

/** 模型维度统计行 */
export interface ModelStatisticsItem {
  model_name: string
  request_count: number
  total_cost: number
  total_tokens: number
  avg_response_time: number
}

/** 智能体维度统计行 */
export interface AgentStatisticsItem {
  agent_id: string
  request_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost: number
  avg_response_time: number
}

/** 时间序列点 */
export interface TimeSeriesItem {
  timestamp: string
  requests: number
  cost: number
  tokens: number
}

/** 近期活动行 */
export interface RecentActivityItem {
  timestamp: string
  model: string
  request_type: string
  tokens: number
  cost: number
  time_cost: number
  status: string
}

/** 智能体统计聚合（home 仪表盘扩展字段） */
export interface AgentStatsInfo {
  total_agents: number
  active_agents: number
  total_active_sessions: number
}

/** dashboard 端点响应 */
export interface DashboardData {
  summary: DashboardSummary
  model_stats: ModelStatisticsItem[]
  hourly_data: TimeSeriesItem[]
  daily_data: TimeSeriesItem[]
  recent_activity: RecentActivityItem[]
  agent_stats?: AgentStatsInfo
}

/** agents 端点响应 */
export interface AgentStatisticsResponse {
  hours: number
  agents: AgentStatisticsItem[]
}

/** 拉取仪表盘统计（summary + 模型统计 + 时间序列） */
export function getDashboardData(hours: number): Promise<DashboardData> {
  return backendApi.get<DashboardData>('/api/webui/statistics/dashboard', { query: { hours } })
}

/** 拉取智能体维度统计 */
export function getAgentStatistics(hours: number): Promise<AgentStatisticsResponse> {
  return backendApi.get<AgentStatisticsResponse>('/api/webui/statistics/agents', { query: { hours } })
}

/** 导出统计 CSV（只读导出——spec.md §4.3 #2） */
export function exportStatistics(hours: number, format: 'csv'): Promise<Blob> {
  return backendApi.get<Blob>('/api/webui/statistics/export', {
    query: { hours, format },
    parse: 'blob',
    errorMessage: 'CSV 导出失败',
  })
}
