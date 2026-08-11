/**
 * ChatStreamMonitor 测试（T1-6-6 测试先行）
 *
 * 核心验证（design.md §2.4）：
 * - 聊天流列表渲染（名称/智能体/消息数/相对时间）
 * - 排序切换（last_active / message_count）
 * - 三态（loading / empty / 数据）
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const { mockGetChatStreams } = vi.hoisted(() => ({
  mockGetChatStreams: vi.fn(),
}))

vi.mock('@/lib/chat-management-api', () => ({
  getChatStreams: mockGetChatStreams,
}))

import { ChatStreamMonitor } from '../chat-stream-monitor'
import type { ChatStream } from '@/lib/chat-management-api'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeStream(overrides: Partial<ChatStream> = {}): ChatStream {
  const now = Date.now() / 1000
  return {
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
    created_at: now - 3600,
    last_active_at: now - 60,
    latest_message: '',
    latest_message_at: now - 60,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetChatStreams.mockResolvedValue([
    makeStream({ session_id: 'sess-1', display_name: '聊天流 A', message_count: 10, last_active_at: Date.now() / 1000 - 60 }),
    makeStream({ session_id: 'sess-2', display_name: '聊天流 B', message_count: 50, last_active_at: Date.now() / 1000 - 7200 }),
  ])
})

describe('ChatStreamMonitor', () => {
  it('聊天流列表渲染（名称/智能体/消息数）', async () => {
    render(<ChatStreamMonitor />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('聊天流 A')).toBeInTheDocument()
    })
    expect(screen.getByText('聊天流 B')).toBeInTheDocument()
    expect(screen.getAllByText('麦麦').length).toBeGreaterThan(0)
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('50')).toBeInTheDocument()
  })

  it('空列表显示空态', async () => {
    mockGetChatStreams.mockResolvedValue([])
    render(<ChatStreamMonitor />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('monitor.chatStream.empty')).toBeInTheDocument()
    })
  })

  it('按 message_count 排序（点击按钮降序 → 再点升序）', async () => {
    const user = userEvent.setup()
    render(<ChatStreamMonitor />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('聊天流 A')).toBeInTheDocument()
    })

    await user.click(screen.getByText('monitor.chatStream.messageCount'))

    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('聊天流 B')

    await user.click(screen.getByText('monitor.chatStream.messageCount'))
    const rowsAsc = screen.getAllByRole('row').slice(1)
    expect(rowsAsc[0]).toHaveTextContent('聊天流 A')
  })
})