import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { MCPSettingsPage } from '../index'

vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn().mockResolvedValue({ mcp: { servers: [{ name: 'test-server', enabled: true, transport: 'stdio', command: 'node' }] } }),
  updateBotConfigSection: vi.fn().mockResolvedValue({ success: true }),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R2-3-6：/mcp-settings MCP 设置页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染 PageShell + 标题', async () => {
    render(<MCPSettingsPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('sidebar.menu.mcpSettings')).toBeInTheDocument())
  })

  it('保存按钮渲染', async () => {
    render(<MCPSettingsPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('mcp-save')).toBeInTheDocument())
  })

  it('添加服务按钮渲染', async () => {
    render(<MCPSettingsPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('mcp-add-server')).toBeInTheDocument())
  })
})