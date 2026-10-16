import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { BotConfigPage } from '../index'

const { mockConfig, mockSchema } = vi.hoisted(() => ({
  mockConfig: { personality: { name: '麦麦' }, reply_style: { style: 'default' }, behavior_style: { mode: 'chat' } },
  mockSchema: { className: 'BotConfig', fields: [], nested: {} },
}))

// 注：`getBotConfigRaw` / `updateBotConfigRaw` 已于 5 段随 raw 端点一并删除，
// 这里不再 mock 它们（mock 一个已不存在的函数 = 测一个不存在的东西）。
vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn().mockResolvedValue(mockConfig),
  getBotConfigSchema: vi.fn().mockResolvedValue(mockSchema),
  updateBotConfig: vi.fn().mockResolvedValue({ success: true }),
  updateBotConfigSection: vi.fn().mockResolvedValue({ success: true }),
}))

vi.mock('react-i18next', () => ({
  // `i18n` 必须给：真实 useTranslation() 一定返回它，详细模式要用 i18n.language 解析 LocalizedText
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'zh-CN' } }),
}))

vi.mock('../../hooks', () => ({
  registerAllConfigHooks: vi.fn(),
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
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

  it('源文件模式——已下线占位（写明原因，不再是编辑器）', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-mode-source')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('bot-mode-source'))

    await waitFor(() => expect(screen.getByTestId('bot-source-mode')).toBeInTheDocument())
    // 占位必须**说明原因**，不能是一片空白
    expect(screen.getByText('「源文件」模式已下线')).toBeInTheDocument()
    // 下线后不许再渲染编辑器——留着它就等于"点进去才发现坏了"
    expect(screen.queryByTestId('code-editor')).not.toBeInTheDocument()
  })

  it('顶部工具栏——刷新按钮', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-refresh')).toBeInTheDocument())
  })

  it('源文件模式——不再有保存按钮（不许留一个点了报错的按钮）', async () => {
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('bot-mode-source')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('bot-mode-source'))
    await waitFor(() => expect(screen.getByTestId('bot-source-mode')).toBeInTheDocument())

    expect(screen.queryByTestId('bot-save-raw')).not.toBeInTheDocument()
  })

  // 注：原先这里有一条"下线后不再调用 raw 端点（防复活）"——它断言的是
  // `api.getBotConfigRaw` / `api.updateBotConfigRaw` 未被调用。那两个函数已随端点删除，
  // 引用它们本身就是编译错误 ⇒ 该用例没有存在余地，已删除。
  // "端点不许复活"的守门在**后端**：`pytests/webui/test_config_seam.py::TestRawEndpointsAreRetired`
  // （断言四个路由 404 + 路由表里不再注册），那里才是判据的落点。

  it('fieldHooks 注册（mount 时调用 registerAllConfigHooks）', async () => {
    const { registerAllConfigHooks } = await import('../../hooks')
    render(<BotConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(registerAllConfigHooks).toHaveBeenCalled())
  })
})