/**
 * DeepSeekMonitorPage 测试（T1-2-2 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 6 端点数据展示：overview / budget / cache / batch / cost / monthly-report
 * - 三态：loading / error / empty
 * - agent Select 渲染 + 切换
 * - mock 数据严格匹配接口类型（R4-2 教训 #9/#10——补全必需字段）
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const {
  mockGetDeepSeekOverview,
  mockGetAgentBudget,
  mockGetAgentCacheStats,
  mockGetBatchOverview,
  mockGetAgentCost,
  mockGetMonthlyCostReport,
  mockGetAgentList,
} = vi.hoisted(() => ({
  mockGetDeepSeekOverview: vi.fn(),
  mockGetAgentBudget: vi.fn(),
  mockGetAgentCacheStats: vi.fn(),
  mockGetBatchOverview: vi.fn(),
  mockGetAgentCost: vi.fn(),
  mockGetMonthlyCostReport: vi.fn(),
  mockGetAgentList: vi.fn(),
}))

vi.mock('@/lib/deepseek-api', () => ({
  getDeepSeekOverview: mockGetDeepSeekOverview,
  getAgentBudget: mockGetAgentBudget,
  getAgentCacheStats: mockGetAgentCacheStats,
  getBatchOverview: mockGetBatchOverview,
  getAgentCost: mockGetAgentCost,
  getMonthlyCostReport: mockGetMonthlyCostReport,
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
}))

import type {
  AgentCostInfo,
  BatchOverviewInfo,
  CacheStatsInfo,
  DeepSeekOverviewInfo,
  MonthlyReportInfo,
  TokenBudgetInfo,
} from '@/lib/deepseek-api'
import type { AgentConfigInfo } from '@/lib/agent-api'

import { DeepSeekMonitorPage } from '../index'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeOverview(): DeepSeekOverviewInfo {
  return {
    total_agents: 3,
    agents_with_budget: 2,
    agents_with_cache: 1,
    batch_api_available: true,
    total_cost_30d: 12.34,
    avg_cache_hit_rate: 0.875,
  }
}

function makeBudget(): TokenBudgetInfo {
  return {
    agent_id: 'agent-a',
    model_context_window: 32000,
    segments: [
      { segment: 'identity', ratio: 0.5, token_limit: 16000 },
      { segment: 'history', ratio: 0.3, token_limit: 9600 },
      { segment: 'reserved', ratio: 0.2, token_limit: 6400 },
    ],
  }
}

function makeCache(): CacheStatsInfo {
  return {
    agent_id: 'agent-a',
    hit_tokens: 8000,
    miss_tokens: 2000,
    hit_rate: 0.8,
    prefix_cache_enabled: true,
  }
}

function makeBatch(): BatchOverviewInfo {
  return {
    api_available: true,
    pending_count: 2,
    degraded_count: 1,
    recent_tasks: [
      {
        task_id: 'task-1',
        agent_id: 'agent-a',
        task_type: 'dream_consolidation',
        status: 'completed',
        priority: 'normal',
        degraded_to_realtime: false,
        created_at: 1700000000,
      },
      {
        task_id: 'task-2',
        agent_id: 'agent-b',
        task_type: 'profile_update',
        status: 'processing',
        priority: 'high',
        degraded_to_realtime: true,
        created_at: 1700000100,
      },
    ],
  }
}

function makeCost(): AgentCostInfo {
  return {
    agent_id: 'agent-a',
    total_cost: 6.5,
    total_input_tokens: 100000,
    total_output_tokens: 50000,
    total_cache_hit_tokens: 30000,
  }
}

function makeReport(): MonthlyReportInfo {
  return {
    by_agent: {
      'agent-a': { cost: 5.25, input_tokens: 100000, output_tokens: 50000 },
      'agent-b': { cost: 2.1, input_tokens: 40000, output_tokens: 20000 },
    },
    by_task_type: {
      dream_consolidation: { cost: 4, input_tokens: 80000, output_tokens: 40000 },
    },
  }
}

function makeAgents(): AgentConfigInfo[] {
  return [
    {
      agent_id: 'agent-a',
      display_name: '麦麦',
      personality: '温柔',
      reply_style: '活泼',
      is_default: true,
      color: '#55AB49',
      emotion_baseline: { happy: 0.5 },
      emotion_decay_rate: 0.9,
      relationship_growth_rate: 0.1,
      talk_value_modifier: 1.0,
      memory_focus_areas: ['chat'],
      internal_relationships: [],
      anti_mechanization_rules: [],
    },
    {
      agent_id: 'agent-b',
      display_name: '小助手',
      personality: '冷静',
      reply_style: '简洁',
      is_default: false,
      color: '#3b82f6',
      emotion_baseline: { calm: 0.6 },
      emotion_decay_rate: 0.8,
      relationship_growth_rate: 0.05,
      talk_value_modifier: 0.8,
      memory_focus_areas: ['chat'],
      internal_relationships: [],
      anti_mechanization_rules: [],
    },
  ]
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetAgentList.mockResolvedValue(makeAgents())
  mockGetDeepSeekOverview.mockResolvedValue(makeOverview())
  mockGetAgentBudget.mockResolvedValue(makeBudget())
  mockGetAgentCacheStats.mockResolvedValue(makeCache())
  mockGetBatchOverview.mockResolvedValue(makeBatch())
  mockGetAgentCost.mockResolvedValue(makeCost())
  mockGetMonthlyCostReport.mockResolvedValue(makeReport())
})

describe('DeepSeekMonitorPage', () => {
  it('PageShell 渲染 + i18n 标题', async () => {
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.deepseek.title')).toBeInTheDocument()
  })

  it('概览卡片展示 4 项指标（智能体数/缓存命中率/30日成本/批处理API）', async () => {
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument()
    })
    expect(screen.getByText('智能体数')).toBeInTheDocument()
    expect(screen.getByText('缓存命中率')).toBeInTheDocument()
    expect(screen.getByText((c) => c.includes('87.5'))).toBeInTheDocument()
    expect(screen.getByText('30日成本')).toBeInTheDocument()
    expect(screen.getByText('¥12.34')).toBeInTheDocument()
    expect(screen.getByText('批处理API')).toBeInTheDocument()
    expect(screen.getByText('可用')).toBeInTheDocument()
  })

  it('agent Select 渲染默认智能体', async () => {
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('麦麦')).toBeInTheDocument()
    })
  })

  it('四个 Tab 标签渲染（预算/缓存/批处理/成本）', async () => {
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByText('monitor.deepseek.budget')).toBeInTheDocument()
    expect(screen.getByText('monitor.deepseek.cache')).toBeInTheDocument()
    expect(screen.getByText('批处理')).toBeInTheDocument()
    expect(screen.getByText('monitor.deepseek.cost')).toBeInTheDocument()
  })

  it('预算面板：上下文窗口 + segment 段名', async () => {
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText((c) => c.includes('32.0K'))).toBeInTheDocument()
    })
    expect(screen.getAllByText('人设注入').length).toBeGreaterThan(0)
    expect(screen.getAllByText('对话历史').length).toBeGreaterThan(0)
    expect(screen.getAllByText('预留').length).toBeGreaterThan(0)
  })

  it('缓存面板：命中率 + 启用徽标', async () => {
    const user = userEvent.setup()
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('tab', { name: 'monitor.deepseek.cache' }))

    await waitFor(() => {
      expect(mockGetAgentCacheStats).toHaveBeenCalledWith('agent-a')
    })
    await waitFor(() => {
      expect(screen.getByText('已启用')).toBeInTheDocument()
    })
    expect(screen.getByText('前缀缓存')).toBeInTheDocument()
    expect(screen.getAllByText((c) => c.includes('80.0')).length).toBeGreaterThan(0)
  })

  it('批处理面板：待处理/降级计数 + 任务行', async () => {
    const user = userEvent.setup()
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('tab', { name: '批处理' }))

    await waitFor(() => {
      expect(mockGetBatchOverview).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByText('Dream巩固')).toBeInTheDocument()
    })
    expect(screen.getByText('画像更新')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('已降级')).toBeInTheDocument()
  })

  it('成本面板：30日总成本 + 月度排行', async () => {
    const user = userEvent.setup()
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('tab', { name: 'monitor.deepseek.cost' }))

    await waitFor(() => {
      expect(mockGetAgentCost).toHaveBeenCalledWith('agent-a')
      expect(mockGetMonthlyCostReport).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByText('月度成本排行')).toBeInTheDocument()
    })
    expect(screen.getByText('¥6.50')).toBeInTheDocument()
    expect(screen.getByText('¥5.25')).toBeInTheDocument()
  })

  it('loading 态：初始显示骨架屏', () => {
    mockGetDeepSeekOverview.mockReturnValue(new Promise(() => {}))
    mockGetAgentList.mockReturnValue(new Promise(() => {}))
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('error 态：overview 请求失败不崩溃、页面降级', async () => {
    mockGetDeepSeekOverview.mockRejectedValue(new Error('overview failed'))
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(mockGetDeepSeekOverview).toHaveBeenCalled()
    })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.deepseek.title')).toBeInTheDocument()
  })

  it('empty 态：预算数据为空显示"暂无预算数据"', async () => {
    mockGetAgentBudget.mockResolvedValue(undefined)
    render(<DeepSeekMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('暂无预算数据')).toBeInTheDocument()
    })
  })
})