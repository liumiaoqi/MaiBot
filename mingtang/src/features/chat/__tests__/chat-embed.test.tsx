/**
 * ChatEmbedPage 嵌入页测试
 *
 * 核心验证：
 * - 无 Layout DOM（使用 embed shell 而非 page-shell）
 * - auth checking 态（加载态"麦麦正在啃食服务器..."）
 * - 已认证态（ChatPage 渲染）
 * - document.title 设置
 */
import { render, screen } from '@testing-library/react'
import { createElement } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const { mockUseAuthGuard } = vi.hoisted(() => ({
  mockUseAuthGuard: vi.fn(),
}))

vi.mock('@/hooks/use-auth', () => ({
  useAuthGuard: mockUseAuthGuard,
}))

vi.mock('../index', () => ({
  ChatPage: () => createElement('div', { 'data-testid': 'chat-page-mock' }),
}))

import { ChatEmbedPage } from '../embed'

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuthGuard.mockReturnValue({ checking: false })
})

describe('ChatEmbedPage', () => {
  it('无 Layout DOM（使用 embed shell 而非 page-shell）', () => {
    const { container } = render(<ChatEmbedPage />)
    expect(screen.queryByTestId('page-shell')).not.toBeInTheDocument()
    expect(container.querySelector('[data-dashboard-shell="embed-chat"]')).not.toBeNull()
  })

  it('auth checking 态显示加载提示', () => {
    mockUseAuthGuard.mockReturnValue({ checking: true })
    render(<ChatEmbedPage />)
    expect(screen.getByText('麦麦正在啃食服务器...')).toBeInTheDocument()
  })

  it('已认证态渲染 ChatPage', () => {
    render(<ChatEmbedPage />)
    expect(screen.getByTestId('chat-page-mock')).toBeInTheDocument()
  })

  it('document.title 设置为 chat.embed.title', () => {
    render(<ChatEmbedPage />)
    expect(document.title).toBe('chat.embed.title')
  })

  it('checking 态不渲染 ChatPage', () => {
    mockUseAuthGuard.mockReturnValue({ checking: true })
    render(<ChatEmbedPage />)
    expect(screen.queryByTestId('chat-page-mock')).not.toBeInTheDocument()
  })
})