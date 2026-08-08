import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { BotConfigPage } from '../index'

const { mockConfig, mockSchema, mockRaw } = vi.hoisted(() => ({
  mockConfig: { personality: { name: '麦麦' }, reply_style: { style: 'default' }, behavior_style: { mode: 'chat' } },
  mockSchema: { className: 'BotConfig', fields: [], nested: {} },
  mockRaw: 'personality = { name = "麦麦" }',
}))

vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn().mockResolvedValue(mockConfig),
  getBotConfigSchema: vi.fn().mockResolvedValue(mockSchema),
  getBotConfigRaw: vi.fn().mockResolvedValue(mockRaw),
  updateBotConfig: vi.fn().mockResolvedValue({ success: true }),
  updateBotConfigSection: vi.fn().mockResolvedValue({ success: true }),
  updateBotConfigRaw: vi.fn().mockResolvedValue({ success: true, message: 'ok', needs_restart: false, restart_required_sections: [] }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('../../hooks', () => ({
  registerAllConfigHooks: vi.fn(),
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

describe('R2-3-3：/config/bot 麦麦设置页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染 PageShell + 标题', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('sidebar.menu.botMainConfig')).toBeInTheDocument())
  })

  it('三模式 Tabs 渲染（核心/详细/源文件）', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-mode-tabs')).toBeInTheDocument())
    expect(screen.getByTestId('bot-mode-core')).toBeInTheDocument()
    expect(screen.getByTestId('bot-mode-detail')).toBeInTheDocument()
    expect(screen.getByTestId('bot-mode-source')).toBeInTheDocument()
  })

  it('核心模式——人格/表达/行为三卡片', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-core-mode')).toBeInTheDocument())
    expect(screen.getByTestId('bot-core-personality')).toBeInTheDocument()
    expect(screen.getByTestId('bot-core-reply_style')).toBeInTheDocument()
    expect(screen.getByTestId('bot-core-behavior_style')).toBeInTheDocument()
  })

  it('切换到详细模式——DynamicConfigTabs', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-mode-detail')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('bot-mode-detail'))
    expect(screen.getByTestId('bot-detail-mode')).toBeInTheDocument()
  })

  it('切换到源文件模式——CodeEditor TOML', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-mode-source')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('bot-mode-source'))
    await waitFor(() => expect(screen.getByTestId('bot-source-mode')).toBeInTheDocument())
    expect(screen.getByTestId('code-editor')).toBeInTheDocument()
  })

  it('顶部工具栏——刷新按钮', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-refresh')).toBeInTheDocument())
  })

  it('源文件模式——保存按钮', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-mode-source')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('bot-mode-source'))
    await waitFor(() => expect(screen.getByTestId('bot-save-raw')).toBeInTheDocument())
  })

  it('fieldHooks 注册（mount 时调用 registerAllConfigHooks）', async () => {
    const { registerAllConfigHooks } = await import('../../hooks')
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(registerAllConfigHooks).toHaveBeenCalled())
  })
})