/**
 * SystemMonitorPage 测试（T1-6-10 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 3 Tabs（system/llm/chat）渲染
 * - ws 连接状态（Wifi/WifiOff → monitor.live / monitor.polling）
 * - 聚合页渲染：system Tab 资源、llm Tab 统计、chat Tab 聊天流
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
  mockBackendGet,
  mockUnifiedWs,
  mockGetChatStreams,
  mockGetSystemResources,
} = vi.hoisted(() => {
  return {
    mockBackendGet: vi.fn(),
    mockUnifiedWs: {
      getStatus: vi.fn(() => 'idle'),
      addEventListener: vi.fn(() => () => {}),
      onConnectionChange: vi.fn(() => () => {}),
      subscribe: vi.fn(() => Promise.resolve({ ok: true })),
      unsubscribe: vi.fn(() => Promise.resolve(null)),
    },
    mockGetChatStreams: vi.fn(),
    mockGetSystemResources: vi.fn(),
  }
})

vi.mock('@/lib/http', () => ({
  backendApi: { get: mockBackendGet },
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: mockUnifiedWs,
}))

vi.mock('@/lib/chat-management-api', () => ({
  getChatStreams: mockGetChatStreams,
}))

vi.mock('@/lib/system-api', () => ({
  getSystemResources: mockGetSystemResources,
}))

import { SystemMonitorPage } from '../index'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

const dashboardData = {
  summary: {
    total_requests: 100,
    total_cost: 12.34,
    total_tokens: 50000,
    online_time: 3600,
    total_messages: 10,
    total_replies: 8,
    avg_response_time: 1.2,
    cost_per_hour: 0.5,
    tokens_per_hour: 1000,
  },
  model_stats: [
    {
      model_name: 'gpt-4o',
      request_count: 60,
      total_cost: 8,
      total_tokens: 30000,
      avg_response_time: 1.1,
    },
  ],
  hourly_data: [],
  daily_data: [],
  recent_activity: [],
}

const agentsData = {
  hours: 24,
  agents: [
    {
      agent_id: 'agent-a',
      request_count: 40,
      total_input_tokens: 10000,
      total_output_tokens: 5000,
      total_cost: 4,
      avg_response_time: 1.3,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  mockBackendGet.mockImplementation((path: string) => {
    if (path.includes('/statistics/dashboard')) return Promise.resolve(dashboardData)
    if (path.includes('/statistics/agents')) return Promise.resolve(agentsData)
    return Promise.reject(new Error('unknown path'))
  })
  mockGetChatStreams.mockResolvedValue([
    {
      id: 1,
      session_id: 'sess-1',
      display_name: '聊天流 A',
      chat_type: 'group',
      target_id: 'group-1',
      platform: 'napcat',
      account_id: null,
      scope: null,
      user_id: null,
      user_nickname: null,
      user_cardname: null,
      group_id: 'group-1',
      group_name: null,
      agent_id: 'agent-a',
      agent_display_name: '麦麦',
      agent_color: '#55AB49',
      message_count: 10,
      expression_count: 0,
      jargon_count: 0,
      created_at: Date.now() / 1000 - 3600,
      last_active_at: Date.now() / 1000 - 60,
      latest_message: '',
      latest_message_at: Date.now() / 1000 - 60,
    },
  ])
  mockGetSystemResources.mockResolvedValue({
    cpu_percent: 30.5,
    memory_percent: 50,
    memory_used: 4096 * 1024 * 1024,
    memory_total: 8192 * 1024 * 1024,
    disk_percent: 60,
    disk_used: 100 * 1024 * 1024 * 1024,
    disk_total: 200 * 1024 * 1024 * 1024,
    database_size: 1024 * 1024 * 1024,
    timestamp: Date.now(),
  })
})

describe('SystemMonitorPage', () => {
  it('PageShell 渲染 + 3 Tabs', async () => {
    render(<SystemMonitorPage />, { wrapper: createWrapper() })

    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('monitor.tabs.system')).toBeInTheDocument()
    expect(screen.getByText('monitor.tabs.llm')).toBeInTheDocument()
    expect(screen.getByText('monitor.tabs.chat')).toBeInTheDocument()
  })

  it('默认 system Tab 渲染系统资源', async () => {
    render(<SystemMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText((c) => c.includes('30.5'))).toBeInTheDocument()
    })
    expect(screen.getByText('monitor.systemResources.cpu')).toBeInTheDocument()
  })

  it('ws 断开时显示轮询状态', async () => {
    render(<SystemMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('monitor.polling')).toBeInTheDocument()
    })
  })

  it('ws 连接时显示实时状态', async () => {
    mockUnifiedWs.getStatus.mockReturnValue('connected')
    render(<SystemMonitorPage />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('monitor.live')).toBeInTheDocument()
    })
  })

  it('切到 llm Tab 渲染统计卡片 + 模型表格', async () => {
    const user = userEvent.setup()
    render(<SystemMonitorPage />, { wrapper: createWrapper() })

    await user.click(screen.getByText('monitor.tabs.llm'))

    await waitFor(() => {
      expect(screen.getByText('monitor.llm.totalRequests')).toBeInTheDocument()
    })
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
    expect(screen.getByText('monitor.llm.modelStats')).toBeInTheDocument()
    expect(screen.getByText('monitor.llm.exportCSV')).toBeInTheDocument()
  })

  it('切到 chat Tab 渲染聊天流列表', async () => {
    const user = userEvent.setup()
    render(<SystemMonitorPage />, { wrapper: createWrapper() })

    await user.click(screen.getByText('monitor.tabs.chat'))

    await waitFor(() => {
      expect(screen.getByText('聊天流 A')).toBeInTheDocument()
    })
    expect(screen.getByText('monitor.chatStream.title')).toBeInTheDocument()
  })
})