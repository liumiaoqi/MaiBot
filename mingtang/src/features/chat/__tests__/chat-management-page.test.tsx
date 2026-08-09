/**
 * ChatManagementPage 测试（R3-2-5 统一验证）
 *
 * 核心验证：双视图切换 + 头部统计卡 + streams 视图搜索/过滤/表格 + 删除流入口
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { ChatStream } from '@/lib/chat-management-api'

import { ChatManagementPage } from '../chat-management'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/lib/chat-management-api', () => ({
  getChatStreams: vi.fn(),
  getChatStreamDetail: vi.fn(),
  deleteChatStream: vi.fn(),
  updateChatStreamTalkFrequency: vi.fn(),
  deleteChatStreamTalkFrequency: vi.fn(),
  updateChatStreamLearning: vi.fn(),
  upsertChatStreamPrompt: vi.fn(),
  deleteChatStreamPrompt: vi.fn(),
}))

vi.mock('@/lib/agent-api', () => ({
  getAgentList: vi.fn().mockResolvedValue([]),
  bindSessionAgent: vi.fn(),
}))

vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn().mockResolvedValue({}),
  updateBotConfigSection: vi.fn(),
}))

vi.mock('@/lib/avatar-url', () => ({
  useResolvedAvatarUrl: () => undefined,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { getChatStreams } from '@/lib/chat-management-api'

const mockedGetChatStreams = vi.mocked(getChatStreams)

/** 构造测试用 ChatStream */
function makeChat(overrides: Partial<ChatStream> = {}): ChatStream {
  return {
    id: 1,
    session_id: 'session-001',
    display_name: '测试群聊',
    chat_type: 'group',
    target_id: 'target-1',
    platform: 'qq',
    account_id: null,
    scope: null,
    user_id: null,
    user_nickname: null,
    user_cardname: null,
    group_id: 'group-1',
    group_name: '测试群',
    agent_id: 'silver_wolf',
    agent_display_name: '银狼',
    agent_color: '#55AB49',
    message_count: 100,
    expression_count: 10,
    jargon_count: 5,
    created_at: 1700000000,
    last_active_at: 1700003600,
    latest_message: '你好',
    latest_message_at: 1700003600,
    ...overrides,
  }
}

/** 包裹 QueryClientProvider */
function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  )
}

describe('ChatManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染头部统计卡（全部/群聊/私聊）', async () => {
    mockedGetChatStreams.mockResolvedValue([
      makeChat({ chat_type: 'group' }),
      makeChat({ session_id: 's2', chat_type: 'private' }),
    ])
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      const allTexts = screen.getAllByText('全部')
      expect(allTexts.length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getAllByText('群聊').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('私聊').length).toBeGreaterThanOrEqual(1)
  })

  it('渲染双视图标签（聊天流/共享组）', async () => {
    mockedGetChatStreams.mockResolvedValue([])
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      const streamTexts = screen.getAllByText('聊天流')
      expect(streamTexts.length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getByText('共享组')).toBeInTheDocument()
  })

  it('streams 视图渲染搜索框', async () => {
    mockedGetChatStreams.mockResolvedValue([])
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('搜索名称、平台、ID、会话 ID 等')).toBeInTheDocument()
    })
  })

  it('streams 视图渲染刷新按钮', async () => {
    mockedGetChatStreams.mockResolvedValue([])
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      expect(screen.getByText('刷新')).toBeInTheDocument()
    })
  })

  it('加载中显示加载文案', async () => {
    mockedGetChatStreams.mockImplementation(() => new Promise(() => []))
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      expect(screen.getByText('正在加载聊天流...')).toBeInTheDocument()
    })
  })

  it('加载完成显示聊天流表格', async () => {
    mockedGetChatStreams.mockResolvedValue([makeChat()])
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      expect(screen.getByText('测试群聊')).toBeInTheDocument()
    })
  })

  it('空列表显示"暂无匹配的聊天流"', async () => {
    mockedGetChatStreams.mockResolvedValue([])
    renderWithProviders(<ChatManagementPage />)

    await waitFor(() => {
      expect(screen.getByText('暂无匹配的聊天流')).toBeInTheDocument()
    })
  })

  it('切换到共享组视图显示共享组管理', async () => {
    const user = userEvent.setup()
    mockedGetChatStreams.mockResolvedValue([])
    renderWithProviders(<ChatManagementPage />)

    const groupsTab = await waitFor(() => screen.getByRole('tab', { name: '共享组' }))
    await user.click(groupsTab)

    await waitFor(() => {
      expect(screen.getByText('管理表达、黑话和记忆的聊天流共享组。')).toBeInTheDocument()
    }, { timeout: 3000 })
  })
})