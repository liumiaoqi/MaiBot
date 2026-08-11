/**
 * SubAgentMonitorPage 测试（T1-5-2 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 子智能体执行统计（总执行/输入输出 Token/缓存命中率）
 * - 类型分布 + 状态分布渲染
 * - 执行记录表（类型/智能体/状态/时间/耗时/摘要）+ 三态
 */
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: { select: (s: { location: { search: Record<string, unknown> } }) => unknown }) =>
    select({ location: { search: {} } }),
}))

const { mockGetAgentList, mockGetSubAgentRecords, mockGetSubAgentStats } = vi.hoisted(() => ({
  mockGetAgentList: vi.fn(),
  mockGetSubAgentRecords: vi.fn(),
  mockGetSubAgentStats: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: mockGetAgentList,
  getSubAgentRecords: mockGetSubAgentRecords,
  getSubAgentStats: mockGetSubAgentStats,
}))

import { SubAgentMonitorPage } from '../index'
import type { AgentConfigInfo, SubAgentRecord, SubAgentStats } from '@/lib/agent-api'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeAgent(id: string, name: string): AgentConfigInfo {
  return {
    agent_id: id,
    display_name: name,
    personality: '温柔',
    reply_style: '活泼',
    is_default: false,
    color: '#55AB49',
    emotion_baseline: { happy: 0.5, calm: 0.4 },
    emotion_decay_rate: 0.9,
    relationship_growth_rate: 0.1,
    talk_value_modifier: 1.0,
    memory_focus_areas: ['chat'],
    internal_relationships: [],
    anti_mechanization_rules: [],
  }
}

function makeStats(): SubAgentStats {
  return {
    total_executions: 42,
    by_type: { dream: 30, compaction: 10, 'checkpoint-writer': 2 },
    by_status: { completed: 40, failed: 2 },
    total_input_tokens: 1500,
    total_output_tokens: 800,
    total_cache_hit_tokens: 500,
  }
}

function makeRecord(overrides: Partial<SubAgentRecord> = {}): SubAgentRecord {
  return {
    id: 1,
    subagent_id: 'sub-1',
    agent_id: 'agent-a',
    subagent_type: 'dream',
    session_id: null,
    lifecycle: 'completed',
    status: 'completed',
    trigger_type: 'time',
    trigger_reason: '定时触发',
    fork_context_captured: true,
    input_tokens: 1500,
    output_tokens: 800,
    cache_hit_tokens: 500,
    started_at: '2026-08-11T10:00:00',
    completed_at: '2026-08-11T10:01:00',
    error_message: '',
    result_summary: '执行完成',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetAgentList.mockResolvedValue([makeAgent('agent-a', '麦麦')])
  mockGetSubAgentStats.mockResolvedValue(makeStats())
  mockGetSubAgentRecords.mockResolvedValue([makeRecord()])
})

describe('SubAgentMonitorPage', () => {
  it('PageShell 渲染 + 标题', async () => {
    render(<SubAgentMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.subagent.title')).toBeInTheDocument()
  })

  it('统计卡片渲染（总执行/输入输出 Token/缓存命中率）', async () => {
    render(<SubAgentMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument()
    })
    expect(screen.getByText('总执行次数')).toBeInTheDocument()
    expect(screen.getAllByText('1.5K').length).toBeGreaterThan(0)
    expect(screen.getAllByText('800').length).toBeGreaterThan(0)
    expect(screen.getByText((c) => c.includes('33.3'))).toBeInTheDocument()
  })

  it('类型分布 + 状态分布渲染', async () => {
    render(<SubAgentMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getAllByText('Dream 巩固').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('按类型分布')).toBeInTheDocument()
    expect(screen.getByText('Compaction 压缩')).toBeInTheDocument()
    expect(screen.getByText('按状态分布')).toBeInTheDocument()
    expect(screen.getAllByText('已完成').length).toBeGreaterThan(0)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('执行记录表渲染（类型/状态/摘要）', async () => {
    render(<SubAgentMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('执行完成')).toBeInTheDocument()
    })
    expect(screen.getByText('执行记录')).toBeInTheDocument()
    expect(screen.getByText('共 1 条')).toBeInTheDocument()
    expect(screen.getByText('agent-a')).toBeInTheDocument()
  })

  it('无执行记录时显示空态', async () => {
    mockGetSubAgentRecords.mockResolvedValue([])
    render(<SubAgentMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('暂无执行记录')).toBeInTheDocument()
    })
  })

  it('stats 为空时统计卡片显示默认值', async () => {
    mockGetSubAgentStats.mockResolvedValue({
      total_executions: 0,
      by_type: {},
      by_status: {},
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_cache_hit_tokens: 0,
    })
    render(<SubAgentMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText((c) => c.includes('0.0'))).toBeInTheDocument()
    })
    expect(screen.getAllByText('暂无数据').length).toBeGreaterThan(0)
  })
})