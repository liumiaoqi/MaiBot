/**
 * JargonManagementPage 黑话管理页测试（R4-1-2-6 测试先行）
 *
 * 核心验证：页面渲染 + 统计 Tabs + 搜索 + 列表 + 创建对话框
 */
import type { ReactNode } from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const {
  mockGetJargonList,
  mockGetJargonStats,
  mockGetJargonChatList,
  mockGetJargonDetail,
  mockDeleteJargon,
  mockBatchDeleteJargons,
  mockBatchSetJargonStatus,
  mockCreateJargon,
  mockUpdateJargon,
} = vi.hoisted(() => ({
  mockGetJargonList: vi.fn(),
  mockGetJargonStats: vi.fn(),
  mockGetJargonChatList: vi.fn(),
  mockGetJargonDetail: vi.fn(),
  mockDeleteJargon: vi.fn(),
  mockBatchDeleteJargons: vi.fn(),
  mockBatchSetJargonStatus: vi.fn(),
  mockCreateJargon: vi.fn(),
  mockUpdateJargon: vi.fn(),
}))

vi.mock('@/lib/jargon-api', () => ({
  getJargonList: mockGetJargonList,
  getJargonStats: mockGetJargonStats,
  getJargonChatList: mockGetJargonChatList,
  getJargonDetail: mockGetJargonDetail,
  deleteJargon: mockDeleteJargon,
  batchDeleteJargons: mockBatchDeleteJargons,
  batchSetJargonStatus: mockBatchSetJargonStatus,
  createJargon: mockCreateJargon,
  updateJargon: mockUpdateJargon,
}))

import { JargonManagementPage } from '../index'
import type { Jargon, JargonStats, JargonChatInfo } from '@/types/jargon'

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'QueryWrapper'
  return Wrapper
}

function makeJargon(overrides: Partial<Jargon> = {}): Jargon {
  return {
    id: 1,
    content: '测试黑话',
    meaning: '测试含义',
    session_id: 'session-1',
    session_ids: ['session-1'],
    chat_name: '测试聊天',
    chat_names: ['测试聊天'],
    is_global: false,
    count: 5,
    is_jargon: true,
    is_legacy_empty_meaning: false,
    is_complete: false,
    created_by: 'AI',
    created_timestamp: '2024-01-01T00:00:00Z',
    updated_timestamp: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeStats(): JargonStats {
  return {
    total: 100,
    confirmed_jargon: 60,
    confirmed_not_jargon: 20,
    manual_jargon: 10,
    global_count: 5,
    complete_count: 80,
    chat_count: 3,
    top_chats: { '聊天A': 50, '聊天B': 30 },
  }
}

function makeChatList(): JargonChatInfo[] {
  return [
    { session_id: 'session-1', chat_name: '聊天A', platform: 'qq', is_group: true },
    { session_id: 'session-2', chat_name: '聊天B', platform: 'qq', is_group: false },
  ]
}

function setupMocks() {
  mockGetJargonList.mockResolvedValue({
    success: true,
    total: 1,
    page: 1,
    page_size: 20,
    data: [makeJargon()],
  })
  mockGetJargonStats.mockResolvedValue({
    success: true,
    data: makeStats(),
  })
  mockGetJargonChatList.mockResolvedValue({
    success: true,
    data: makeChatList(),
  })
}

function renderPage() {
  setupMocks()
  return render(<JargonManagementPage />, { wrapper: makeWrapper() })
}

describe('JargonManagementPage 黑话管理页', () => {
  describe('页面渲染', () => {
    it('渲染统计 Tabs（6 个）', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('总数量')).toBeInTheDocument()
      })
      expect(screen.getByText('已确认黑话')).toBeInTheDocument()
      expect(screen.getByText('无黑话')).toBeInTheDocument()
      expect(screen.getByText('手动黑话')).toBeInTheDocument()
      expect(screen.getByText('全局黑话')).toBeInTheDocument()
      expect(screen.getByText('推断完成')).toBeInTheDocument()
    })

    it('渲染搜索输入框', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByPlaceholderText('搜索黑话内容...')).toBeInTheDocument()
      })
    })

    it('渲染新增黑话按钮', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByLabelText('新增黑话')).toBeInTheDocument()
      })
    })

    it('渲染聊天范围侧边栏', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('全部聊天')).toBeInTheDocument()
      })
    })
  })

  describe('统计数据显示', () => {
    it('统计数字正确展示', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('100')).toBeInTheDocument()
      })
      expect(screen.getByText('60')).toBeInTheDocument()
    })
  })

  describe('黑话列表', () => {
    it('渲染黑话列表数据', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('测试黑话').length).toBeGreaterThan(0)
      })
    })

    it('渲染黑话含义', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('测试含义').length).toBeGreaterThan(0)
      })
    })
  })

  describe('搜索交互', () => {
    it('输入搜索文本更新 searchInput', async () => {
      renderPage()

      const searchInput = await screen.findByPlaceholderText('搜索黑话内容...')
      fireEvent.change(searchInput, { target: { value: '关键词' } })

      expect(searchInput).toHaveValue('关键词')
    })
  })

  describe('创建对话框', () => {
    it('点击新增按钮打开创建对话框', async () => {
      renderPage()

      const addButton = await screen.findByLabelText('新增黑话')
      fireEvent.click(addButton)

      await waitFor(() => {
        expect(screen.getByText('新增黑话')).toBeInTheDocument()
      })
    })
  })
})