/**
 * DeleteChatStreamDialog 测试（R3-2-4 测试先行）
 *
 * 核心验证：严肃确认（必须输入完整 session_id）+ 分阶段进度 + 明细汇总
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { ChatStream } from '@/lib/chat-management-api'

import { DeleteChatStreamDialog, formatDeleteSummary } from '../components/delete-chat-stream-dialog'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/lib/chat-management-api', () => ({
  deleteChatStream: vi.fn(),
}))

import { deleteChatStream } from '@/lib/chat-management-api'

const mockedDeleteChatStream = vi.mocked(deleteChatStream)

/** 构造测试用 ChatStream */
function makeChat(overrides: Partial<ChatStream> = {}): ChatStream {
  return {
    id: 1,
    session_id: 'test-session-001',
    display_name: '测试聊天',
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

describe('formatDeleteSummary', () => {
  it('无可见项返回"未发现可清理的数据"', () => {
    expect(formatDeleteSummary({ session_id: 's1', deleted_total: 0, items: [] })).toBe('未发现可清理的数据。')
  })

  it('普通项格式化', () => {
    expect(formatDeleteSummary({
      session_id: 's1',
      deleted_total: 50,
      items: [
        { key: 'messages', label: '消息', count: 50, unlinked: 0 },
      ],
    })).toBe('消息 50 条')
  })

  it('jargons 项含解除关联', () => {
    expect(formatDeleteSummary({
      session_id: 's1',
      deleted_total: 8,
      items: [
        { key: 'jargons', label: '黑话', count: 5, unlinked: 3 },
      ],
    })).toBe('黑话 删除 5 条，解除关联 3 条')
  })

  it('多项用分号连接', () => {
    expect(formatDeleteSummary({
      session_id: 's1',
      deleted_total: 58,
      items: [
        { key: 'messages', label: '消息', count: 50, unlinked: 0 },
        { key: 'jargons', label: '黑话', count: 5, unlinked: 3 },
      ],
    })).toBe('消息 50 条；黑话 删除 5 条，解除关联 3 条')
  })

  it('count=0 且 unlinked=0 的项不显示', () => {
    expect(formatDeleteSummary({
      session_id: 's1',
      deleted_total: 10,
      items: [
        { key: 'empty', label: '空', count: 0, unlinked: 0 },
        { key: 'messages', label: '消息', count: 10, unlinked: 0 },
      ],
    })).toBe('消息 10 条')
  })
})

describe('DeleteChatStreamDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('chat=null 时不渲染', () => {
    const { container } = renderWithProviders(
      <DeleteChatStreamDialog
        chat={null}
        onDeleted={vi.fn()}
        onOpenChange={vi.fn()}
      />
    )
    expect(container.querySelector('[data-slot="dialog-content"]')).toBeNull()
  })

  it('chat 存在时渲染危险说明框', () => {
    renderWithProviders(
      <DeleteChatStreamDialog
        chat={makeChat()}
        onDeleted={vi.fn()}
        onOpenChange={vi.fn()}
      />
    )
    expect(screen.getByText('将被清理的数据包括：')).toBeInTheDocument()
  })

  it('显示聊天流名称和 session_id', () => {
    const chat = makeChat()
    renderWithProviders(
      <DeleteChatStreamDialog
        chat={chat}
        onDeleted={vi.fn()}
        onOpenChange={vi.fn()}
      />
    )
    expect(screen.getByText('测试聊天')).toBeInTheDocument()
    expect(screen.getByText('test-session-001')).toBeInTheDocument()
  })

  it('未输入 session_id 时删除按钮禁用', () => {
    renderWithProviders(
      <DeleteChatStreamDialog
        chat={makeChat()}
        onDeleted={vi.fn()}
        onOpenChange={vi.fn()}
      />
    )
    const deleteButton = screen.getByText('永久删除')
    expect(deleteButton).toBeDisabled()
  })

  it('输入错误 session_id 时删除按钮仍禁用', () => {
    renderWithProviders(
      <DeleteChatStreamDialog
        chat={makeChat()}
        onDeleted={vi.fn()}
        onOpenChange={vi.fn()}
      />
    )
    const input = screen.getByPlaceholderText('test-session-001')
    fireEvent.change(input, { target: { value: 'wrong-id' } })
    expect(screen.getByText('永久删除')).toBeDisabled()
  })

  it('输入正确 session_id 时删除按钮启用', () => {
    renderWithProviders(
      <DeleteChatStreamDialog
        chat={makeChat()}
        onDeleted={vi.fn()}
        onOpenChange={vi.fn()}
      />
    )
    const input = screen.getByPlaceholderText('test-session-001')
    fireEvent.change(input, { target: { value: 'test-session-001' } })
    expect(screen.getByText('永久删除')).not.toBeDisabled()
  })

  it('点击删除后调用 deleteChatStream 并显示进度', async () => {
    mockedDeleteChatStream.mockResolvedValue({
      session_id: 'test-session-001',
      deleted_total: 50,
      items: [{ key: 'messages', label: '消息', count: 50, unlinked: 0 }],
    })
    const onDeleted = vi.fn()
    renderWithProviders(
      <DeleteChatStreamDialog
        chat={makeChat()}
        onDeleted={onDeleted}
        onOpenChange={vi.fn()}
      />
    )
    const input = screen.getByPlaceholderText('test-session-001')
    fireEvent.change(input, { target: { value: 'test-session-001' } })
    fireEvent.click(screen.getByText('永久删除'))

    await waitFor(() => {
      expect(mockedDeleteChatStream).toHaveBeenCalledWith('test-session-001')
    })
    await waitFor(() => {
      expect(onDeleted).toHaveBeenCalledWith('test-session-001')
    })
  })
})